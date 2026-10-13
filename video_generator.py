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

def extract_keyframes_base64(video_path: str, max_frames: int = 2) -> list[str]:
    """Videodan asosiy kadrlarni ajratib, AI ko'rishi uchun base64 formatda qaytaradi."""
    if not video_path or not os.path.exists(video_path):
        return []
    try:
        import imageio.v3 as iio
        from io import BytesIO
        import base64
        frames = list(iio.imiter(video_path))
        if not frames:
            return []
        indices = [len(frames) // 4, len(frames) * 3 // 4] if len(frames) > 4 else [0]
        result = []
        for idx in indices[:max_frames]:
            img = Image.fromarray(frames[idx])
            img.thumbnail((512, 512))
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=75)
            b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
            result.append(b64)
        return result
    except Exception as e:
        print(f"[Keyframe extraction xatosi]: {e}")
        return []

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
            keyframes = extract_keyframes_base64(video_path, max_frames=2) if (download and video_path) else []
            res = {
                'status': 'success',
                'title': info.get('title', ''),
                'description': (info.get('description') or '')[:500],
                'uploader': info.get('uploader', ''),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', ''),
                'video_path': video_path,
                'keyframes_b64': keyframes
            }
            _URL_CACHE[url] = res
            gc.collect()
            return res
    except Exception as e:
        print(f"[yt-dlp xatolik]: {e}")
        return {'status': 'error', 'error': str(e)}

def try_replicate_faceswap(source_image_paths: list, target_video_path: str, output_path: str, instruction: str = "") -> tuple[bool, str]:
    """
    Replicate AI (prunaai/p-video-replace) orqali videodagi odamni yuborilgan rasmga 100% fotorealistik almashtirish.
    Qaytaradi: (success: bool, error_msg: str)
    """
    token = os.environ.get("REPLICATE_API_TOKEN", "") or REPLICATE_API_TOKEN
    if not token:
        return False, "REPLICATE_API_TOKEN topilmadi."
    if not output_path or not source_image_paths or not target_video_path:
        return False, "Kiruvchi video yoki rasmlar yetishmaydi."
        
    try:
        import time
        import replicate
        import requests
        print("[Replicate Video Replace]: Haqiqiy AI Video Replace (prunaai/p-video-replace) boshlandi...")
        
        opened_files = []
        try:
            target_vid_file = open(target_video_path, "rb")
            opened_files.append(target_vid_file)
            
            img_files = []
            for img_p in source_image_paths[:3]:
                if os.path.exists(img_p):
                    f = open(img_p, "rb")
                    opened_files.append(f)
                    img_files.append(f)
                    
            if not img_files:
                return False, "Qahramon rasmlari topilmadi."
                
            pred = replicate.models.predictions.create(
                "prunaai/p-video-replace",
                input={
                    "video": target_vid_file,
                    "images": img_files,
                    "instruction_prompt": instruction or "Replace the character/driver in the video with the person from the reference images seamlessly",
                    "turbo": True,
                    "save_audio": True
                }
            )
            
            for _ in range(80):
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
                    return True, ""
            elif pred.status == "failed":
                return False, f"Replicate AI generatsiya xatosi: {pred.error}"
        finally:
            for f in opened_files:
                try:
                    f.close()
                except Exception:
                    pass
    except Exception as e:
        err_str = str(e)
        print(f"[Replicate Video Replace xatosi]: {err_str}")
        if "402" in err_str or "Insufficient credit" in err_str:
            return False, "Replicate hisobida balans yetarli emas (402 Insufficient credit). AI Video Face-Swap va videodagi odamni almashtirish uchun Replicate.com hisobingizda balans bo'lishi kerak."
        return False, err_str
            
    return False, "Video almashtirish amalga oshmadi."

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
    
    # 1. Agar referans video berilgan bo'lsa (Face-Swap / Video Replace vazifasi)
    if reference_video and os.path.exists(reference_video) and uploaded_images:
        instruction = f"{mavzu}. Replace the actor/driver with the user photo and replace the vehicle if requested."
        ok, err_msg = try_replicate_faceswap(source_image_paths=uploaded_images, target_video_path=reference_video, output_path=output_path, instruction=instruction)
        if ok:
            return fayl_nomi
        else:
            # Soxta yoki stikerli video berish taqiqlanadi! Foydalanuvchiga to'g'ri va haqiqiy xato beriladi.
            raise Exception(err_msg or "AI Video Face-Swap generatsiyasida xatolik yuz berdi.")
            
    # 2. Agar referans video bo'lmasa, Replicate AI Video (minimax/video-01) generatsiyasini sinab ko'ramiz
    prompt_full = f"{mavzu}. " + " ".join([k.get('vizual', '') or k.get('matn', '') for k in kadrlar if isinstance(k, dict)])
    if try_replicate_video(prompt_full, image_path=first_img, output_path=output_path):
        return fayl_nomi

    # 3. Avtonom HD Video Dvigateli (Foydalanuvchi yuklagan rasmlar asosida toza, professional video)
    print(f"[Video Asbob]: {fayl_nomi} yaratilmoqda (Avtonom HD Dvigatel)...")
    
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

    writer = imageio.get_writer(
        output_path,
        fps=fps,
        codec='libx264',
        pixelformat='yuv420p',
        macro_block_size=16
    )

    for s_idx, scene in enumerate(kadrlar):
        s_title = scene.get('sarlavha', '') if isinstance(scene, dict) else ''
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
            elif ref_frames:
                rf = ref_frames[(s_idx * frames_per_scene + f) % len(ref_frames)]
                frame_img = rf.copy()
            else:
                frame_img = Image.new("RGB", (width, height), (15, 23, 42))

            draw = ImageDraw.Draw(frame_img)

            # Agar matn yoki sarlavha bo'lsa, pastda qulay, toza subtitr ko'rsatiladi
            if s_title or s_text:
                title_lines = wrap_text(s_title, font_title, width - 48, draw) if s_title else []
                sub_lines = wrap_text(s_text, font_body, width - 48, draw) if s_text else []
                
                panel_h = 24 + len(title_lines) * 26 + len(sub_lines) * 20
                panel_top = height - panel_h - 18
                draw.rectangle([(16, panel_top), (width - 16, height - 16)], fill=(15, 23, 42), outline=(42, 171, 238), width=1)
                
                curr_y = panel_top + 16
                for line in title_lines:
                    draw.text((width // 2, curr_y), line, fill=(251, 191, 36), font=font_title, anchor="mm")
                    curr_y += 26
                for line in sub_lines:
                    draw.text((width // 2, curr_y), line, fill=(241, 245, 249), font=font_body, anchor="mm")
                    curr_y += 20

            # Progress chizig'i
            overall_progress = (s_idx * frames_per_scene + f + 1) / float(total_scenes * frames_per_scene)
            draw.rectangle([(0, height - 4), (int(width * overall_progress), height)], fill=(42, 171, 238))

            writer.append_data(np.asarray(frame_img))

    writer.close()
    del loaded_images
    del ref_frames
    del scene_images
    gc.collect()
    print(f"[Video Asbob]: {fayl_nomi} muvaffaqiyatli saqlandi!")
    return fayl_nomi
