import os
import gc
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import imageio

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPLICATE_API_TOKEN = os.environ.get("REPLICATE_API_TOKEN", "")
if "REPLICATE_API_TOKEN" not in os.environ and REPLICATE_API_TOKEN:
    os.environ["REPLICATE_API_TOKEN"] = REPLICATE_API_TOKEN

# URL kesh (yt-dlp ikki marta chaqirilmasligi va RAM tejash uchun)
_URL_CACHE = {}

def get_font(size, bold=False):
    """Windows va Linux (Render) uchun mos shriftni topadi."""
    candidates = [
        "C:/Windows/Fonts/calibrib.ttf" if bold else "C:/Windows/Fonts/calibri.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    try:
        return ImageFont.load_default()
    except Exception:
        return None

def wrap_text(text, font, max_width, draw):
    """Matnni ko'rsatilgan kenglikka moslab bir nechta qatorga bo'ladi."""
    if not text:
        return []
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = ' '.join(current_line + [word])
        try:
            bbox = draw.textbbox((0, 0), test_line, font=font)
            w = bbox[2] - bbox[0]
        except Exception:
            w = len(test_line) * 9
            
        if w <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
                current_line = [word]
            else:
                lines.append(word)
                current_line = []
    if current_line:
        lines.append(' '.join(current_line))
    return lines[:3]  # Maksimum 3 qator

def fit_and_crop_rgb(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Rasmni xotirani tejash uchun darhol kerakli o'lchamga (RGB) moslab kesadi."""
    img = img.convert("RGB")
    bw, bh = img.size
    aspect_target = target_w / float(target_h)
    aspect_img = bw / float(bh)
    
    if aspect_img > aspect_target:
        crop_h = bh
        crop_w = int(bh * aspect_target)
    else:
        crop_w = bw
        crop_h = int(bw / aspect_target)
        
    left = max(0, (bw - crop_w) // 2)
    top = max(0, (bh - crop_h) // 2)
    cropped = img.crop((left, top, left + crop_w, top + crop_h))
    return cropped.resize((target_w, target_h), Image.Resampling.BILINEAR)

def extract_video_from_url(url: str, output_folder: str = None, download: bool = False) -> dict:
    """
    Instagram, TikTok, YouTube ssilkasidagi videoni tahlil qiladi va kerak bo'lsa yuklab oladi.
    Xotirani tejash uchun keshdan foydalanadi.
    """
    if not output_folder:
        output_folder = os.path.join(BASE_DIR, 'uploads')
    os.makedirs(output_folder, exist_ok=True)
    
    if url in _URL_CACHE:
        cached = _URL_CACHE[url]
        if not download or (cached.get('video_path') and os.path.exists(cached['video_path'])):
            return cached
            
    try:
        import yt_dlp
        ydl_opts = {
            'outtmpl': os.path.join(output_folder, 'ref_%(id)s.%(ext)s'),
            'format': 'mp4[filesize<15M]/best[filesize<15M]/mp4/best',
            'quiet': True,
            'no_warnings': True
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=download)
            video_path = ydl.prepare_filename(info) if download else None
            res = {
                'status': 'success',
                'title': info.get('title', ''),
                'description': (info.get('description') or '')[:500],
                'uploader': info.get('uploader', ''),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', ''),
                'video_path': video_path
            }
            _URL_CACHE[url] = res
            gc.collect()
            return res
    except Exception as e:
        print(f"[yt-dlp xatolik]: {e}")
        return {'status': 'error', 'error': str(e)}

def try_replicate_faceswap(source_image_path: str, target_video_path: str, output_path: str) -> tuple[bool, bool]:
    """
    Replicate AI orqali videodagi odamning yuzini yangi rasm yuziga almashtirish.
    Qaytaradi: (success: bool, insufficient_credit: bool)
    """
    token = os.environ.get("REPLICATE_API_TOKEN", "") or REPLICATE_API_TOKEN
    if not token or not output_path or not source_image_path or not target_video_path:
        return False, False
        
    try:
        import time
        import replicate
        import requests
        print("[Replicate FaceSwap]: Video Face-Swap boshlandi...")
        
        with open(source_image_path, "rb") as s_img, open(target_video_path, "rb") as t_vid:
            pred = replicate.predictions.create(
                version="50a0a0018673852629578e627576326036b407e0dbd8cf8a0b5028296726dc5c",
                input={
                    "source_image": s_img,
                    "target_video": t_vid,
                    "enhance": True
                }
            )
            
        for _ in range(60):
            if pred.status in ("succeeded", "failed", "canceled"):
                break
            time.sleep(3)
            pred.reload()
            
        if pred.status == "succeeded" and pred.output:
            url = str(pred.output)
            r = requests.get(url, timeout=120)
            if r.status_code == 200:
                with open(output_path, "wb") as f:
                    f.write(r.content)
                return True, False
    except Exception as e:
        err_str = str(e)
        print(f"[Replicate FaceSwap xatosi]: {err_str}")
        if "402" in err_str or "Insufficient credit" in err_str:
            return False, True
            
    return False, False

def try_replicate_video(prompt, image_path=None, output_path=None) -> bool:
    """Agar REPLICATE_API_TOKEN mavjud bo'lsa va balans yetarli bo'lsa, Replicate orqali AI video yaratadi."""
    token = os.environ.get("REPLICATE_API_TOKEN", "") or REPLICATE_API_TOKEN
    if not token or not output_path:
        return False
        
    try:
        import time
        import replicate
        import requests
        print("[Replicate AI]: Video generatsiya boshlandi...")
        
        inp = {
            "prompt": prompt or "High quality cinematic motion, highly detailed 4k, smooth cinematic video",
            "prompt_optimizer": True
        }
        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as img_file:
                inp["first_frame_image"] = img_file
                pred = replicate.models.predictions.create("minimax/video-01", input=inp)
        else:
            pred = replicate.models.predictions.create("minimax/video-01", input=inp)
            
        for _ in range(65):
            if pred.status in ("succeeded", "failed", "canceled"):
                break
            time.sleep(3)
            pred.reload()
            
        if pred.status == "succeeded" and pred.output:
            url = str(pred.output)
            r = requests.get(url, timeout=120)
            if r.status_code == 200:
                with open(output_path, "wb") as f:
                    f.write(r.content)
                return True
    except Exception as e:
        print(f"[Replicate AI] Ogohlantirish: {e}. Avtonom dvigatelga o'tilmoqda.")
        
    return False

def generate_free_ai_image(prompt_text: str, width: int = 480, height: int = 848):
    """Pollinations Flux AI orqali tekin fotorealistik kadr tasvirini yaratadi."""
    try:
        import requests
        import urllib.parse
        from io import BytesIO
        clean_p = urllib.parse.quote(f"Cinematic photorealistic 4k scene, {prompt_text[:180]}")
        url = f"https://image.pollinations.ai/prompt/{clean_p}?width={width}&height={height}&nologo=true&seed={abs(hash(prompt_text)) % 9999}"
        r = requests.get(url, timeout=10)
        if r.status_code == 200 and len(r.content) > 2000:
            img = Image.open(BytesIO(r.content))
            return fit_and_crop_rgb(img, width, height)
    except Exception as e:
        print(f"[AI Image Fallback xatosi]: {e}")
    return None

def render_dynamic_video(fayl_nomi: str, mavzu: str, kadrlar: list, uploaded_images: list = None, vertical: bool = True, reference_video: str = None) -> str:
    """
    Xotirani (RAM < 45MB) tejaydigan, Render Free Tier serverida 100% barqaror ishlovchi HD video dvigateli.
    """
    gc.collect()
    if not fayl_nomi.endswith('.mp4'):
        fayl_nomi = fayl_nomi.replace('.avi', '').replace('.mov', '') + '.mp4'
        
    output_path = os.path.join(BASE_DIR, fayl_nomi)
    first_img = uploaded_images[0] if (uploaded_images and len(uploaded_images) > 0) else None
    
    # 1. Replicate Face-Swap va Video Generatsiyani sinab ko'ramiz
    no_credit = False
    if reference_video and os.path.exists(reference_video) and first_img:
        ok, no_credit = try_replicate_faceswap(source_image_path=first_img, target_video_path=reference_video, output_path=output_path)
        if ok:
            return fayl_nomi
            
    if not no_credit:
        prompt_full = f"{mavzu}. " + " ".join([k.get('vizual', '') or k.get('matn', '') for k in kadrlar if isinstance(k, dict)])
        if try_replicate_video(prompt_full, image_path=first_img, output_path=output_path):
            return fayl_nomi

    # 2. Avtonom Tezkor HD Montaj Dvigateli (Render 512MB RAM uchun maxsus optimallashtirilgan)
    print(f"[Video Asbob]: {fayl_nomi} yaratilmoqda (Avtonom Tezkor Dvigatel)...")
    
    # 16 ga karrali o'lchamlar (H.264 kodek ogohlantirishsiz va minimal RAM bilan ishlashi uchun)
    width = 480 if vertical else 848
    height = 848 if vertical else 480
    fps = 16
    seconds_per_scene = 3
    frames_per_scene = fps * seconds_per_scene  # 48 kadr har bir sahna uchun
    
    # Yuklangan rasmlarni darhol kichraytirib RGB formatda olamiz (RAM tejash)
    loaded_images = []
    if uploaded_images:
        for img_p in uploaded_images:
            if img_p and os.path.exists(img_p):
                try:
                    if img_p.lower().endswith(('.mp4', '.mov', '.avi')):
                        vid_r = imageio.get_reader(img_p)
                        arr = vid_r.get_data(0)
                        loaded_images.append(fit_and_crop_rgb(Image.fromarray(arr), int(width * 1.15), int(height * 1.15)))
                        vid_r.close()
                    else:
                        with Image.open(img_p) as raw_im:
                            loaded_images.append(fit_and_crop_rgb(raw_im, int(width * 1.15), int(height * 1.15)))
                except Exception as e:
                    print("Rasm ochishda xato:", e)
                    
    # Referans videodan eng muhim harakatli kadrlarni (maksimum 32 ta, oldindan kichraytirilgan RGB) olamiz
    ref_frames = []
    if reference_video and os.path.exists(reference_video):
        try:
            ref_reader = imageio.get_reader(reference_video)
            for idx_f, arr in enumerate(ref_reader):
                if idx_f % 3 == 0:
                    ref_frames.append(fit_and_crop_rgb(Image.fromarray(arr), width, height))
                if len(ref_frames) >= 32:
                    break
            ref_reader.close()
        except Exception as e:
            print("Referans video o'qishda xato:", e)
            
    gc.collect()

    # Sahnalar ro'yxatini boyitamiz: barcha yuklangan rasmlar va referans video qatnashishi shart!
    if not kadrlar or not isinstance(kadrlar, list):
        kadrlar = [{"sarlavha": mavzu or "Maxsus Video", "matn": ""}]
        
    # Agar foydalanuvchi 2+ ta rasm yuklagan bo'lsa va kadrlar soni kam bo'lsa, har bir rasm uchun sahna ochamiz
    while len(kadrlar) < len(loaded_images):
        idx_n = len(kadrlar) + 1
        kadrlar.append({"sarlavha": f"{idx_n}-Sahna: Maxsus Ko'rinish", "matn": mavzu or ""})
        
    # Agar referans video bo'lsa, yakuniy dinamik VFX sahnasini qo'shamiz
    if ref_frames and len(kadrlar) <= len(loaded_images):
        kadrlar.append({"sarlavha": "Dinamik Transformatsiya", "matn": mavzu or "Maxsus effekt"})
        
    kadrlar = kadrlar[:4]  # Maksimum 4 sahna (12 soniya)
    total_scenes = len(kadrlar)
    
    # Har bir sahna uchun tasvir tayyorlash
    scene_images = []
    for idx, scene in enumerate(kadrlar):
        if idx < len(loaded_images):
            scene_images.append(loaded_images[idx])
        elif ref_frames and idx == total_scenes - 1:
            scene_images.append(None)  # Jonli referans video oqimi
        elif loaded_images:
            scene_images.append(loaded_images[idx % len(loaded_images)])
        elif ref_frames:
            scene_images.append(None)
        else:
            viz_prompt = (scene.get('vizual') or scene.get('matn') or mavzu) if isinstance(scene, dict) else str(mavzu)
            ai_im = generate_free_ai_image(f"{mavzu}, {viz_prompt}", width=int(width * 1.15), height=int(height * 1.15))
            scene_images.append(ai_im)

    # Shriftlar
    font_badge = get_font(15, bold=True)
    font_title = get_font(22, bold=True)
    font_body = get_font(16, bold=False)

    # PiP (Picture-in-Picture) kichik kartochkalar (referans video ustida foydalanuvchi rasmlarini ko'rsatish uchun)
    pip_thumbs = []
    for im in loaded_images[:2]:
        pip_thumbs.append(fit_and_crop_rgb(im, 110, 110))

    writer = imageio.get_writer(
        output_path,
        fps=fps,
        codec='libx264',
        pixelformat='yuv420p',
        macro_block_size=16
    )

    for s_idx, scene in enumerate(kadrlar):
        s_title = scene.get('sarlavha', f"{s_idx+1}-Kadr") if isinstance(scene, dict) else f"{s_idx+1}-Kadr"
        s_text = scene.get('matn', '') if isinstance(scene, dict) else str(scene)
        static_im = scene_images[s_idx]
        
        for f in range(frames_per_scene):
            t = f / float(frames_per_scene)
            
            if static_im is not None:
                # Ken Burns silliq zoom va pan (static_im 1.15x o'lchamda tayyorlangan)
                sw, sh = static_im.size
                max_dx = max(0, sw - width)
                max_dy = max(0, sh - height)
                ox = int(max_dx * (t if s_idx % 2 == 0 else (1.0 - t)))
                oy = int(max_dy * t * 0.8)
                frame_img = static_im.crop((ox, oy, ox + width, oy + height)).copy()
                
                # Agar referans video ham bo'lsa, burchakda kichik jonli kadr ko'rsatamiz
                if ref_frames:
                    rf = ref_frames[(s_idx * frames_per_scene + f) % len(ref_frames)]
                    rf_small = rf.resize((116, 160), Image.Resampling.BILINEAR)
                    frame_img.paste(rf_small, (width - 132, 76))
            elif ref_frames:
                # Jonli referans video oqimi + foydalanuvchi yuklagan Qahramon va Labo rasmlari PiP burchagida
                rf = ref_frames[(s_idx * frames_per_scene + f) % len(ref_frames)]
                frame_img = rf.copy()
                for p_i, p_thumb in enumerate(pip_thumbs):
                    px = 16 + p_i * 120
                    py = 76
                    frame_img.paste(p_thumb, (px, py))
            else:
                frame_img = Image.new("RGB", (width, height), (15, 23, 42))

            draw = ImageDraw.Draw(frame_img)

            # Yuqori va pastki qora panellar (alpha_composite o'rniga tez va yengil to'g'ridan-to'g'ri chizish)
            draw.rectangle([(0, 0), (width, 62)], fill=(13, 20, 33))
            draw.line([(0, 62), (width, 62)], fill=(42, 171, 238), width=2)
            draw.text((width // 2, 22), "AI EXECUTIVE STUDIO • HD PRODUCTION", fill=(226, 232, 240), font=font_badge, anchor="mm")
            draw.text((width // 2, 44), f"SAHNA {s_idx + 1} / {total_scenes}", fill=(42, 171, 238), font=font_badge, anchor="mm")

            # Pastki subtitr bloki
            title_lines = wrap_text(s_title, font_title, width - 48, draw)
            sub_lines = wrap_text(s_text, font_body, width - 48, draw)
            
            panel_h = 36 + len(title_lines) * 28 + len(sub_lines) * 22
            panel_top = height - panel_h - 14
            draw.rectangle([(12, panel_top), (width - 12, height - 12)], fill=(15, 23, 42), outline=(42, 171, 238), width=1)
            
            curr_y = panel_top + 20
            for line in title_lines:
                draw.text((width // 2, curr_y), line, fill=(251, 191, 36), font=font_title, anchor="mm")
                curr_y += 28
            curr_y += 4
            for line in sub_lines:
                draw.text((width // 2, curr_y), line, fill=(241, 245, 249), font=font_body, anchor="mm")
                curr_y += 22

            # Progress chizig'i
            overall_progress = (s_idx * frames_per_scene + f + 1) / float(total_scenes * frames_per_scene)
            draw.rectangle([(0, height - 5), (int(width * overall_progress), height)], fill=(42, 171, 238))

            writer.append_data(np.asarray(frame_img))

    writer.close()
    del loaded_images
    del ref_frames
    del scene_images
    gc.collect()
    print(f"[Video Asbob]: {fayl_nomi} muvaffaqiyatli saqlandi!")
    return fayl_nomi
