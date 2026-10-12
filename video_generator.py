import os
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import imageio

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPLICATE_API_TOKEN = os.environ.get("REPLICATE_API_TOKEN", "")
if "REPLICATE_API_TOKEN" not in os.environ and REPLICATE_API_TOKEN:
    os.environ["REPLICATE_API_TOKEN"] = REPLICATE_API_TOKEN

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
            w = len(test_line) * 10
            
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
    return lines

def extract_video_from_url(url: str, output_folder: str = None, download: bool = False) -> dict:
    """
    Instagram, TikTok, YouTube ssilkasidagi videoni tahlil qiladi va kerak bo'lsa yuklab oladi.
    """
    if not output_folder:
        output_folder = os.path.join(BASE_DIR, 'uploads')
    os.makedirs(output_folder, exist_ok=True)
    
    try:
        import yt_dlp
        ydl_opts = {
            'outtmpl': os.path.join(output_folder, 'ref_%(id)s.%(ext)s'),
            'format': 'mp4/best',
            'quiet': True,
            'no_warnings': True
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=download)
            video_path = ydl.prepare_filename(info) if download else None
            return {
                'status': 'success',
                'title': info.get('title', ''),
                'description': info.get('description', ''),
                'uploader': info.get('uploader', ''),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', ''),
                'video_path': video_path
            }
    except Exception as e:
        print(f"[yt-dlp xatolik]: {e}")
        return {'status': 'error', 'error': str(e)}

def try_replicate_faceswap(source_image_path: str, target_video_path: str, output_path: str) -> bool:
    """
    Replicate AI orqali videodagi odamning yuzini yangi rasm yuziga almashtirish (Face-Swap).
    """
    token = os.environ.get("REPLICATE_API_TOKEN", "") or REPLICATE_API_TOKEN
    if not token or not output_path or not source_image_path or not target_video_path:
        return False
        
    try:
        import replicate
        import requests
        print("[Replicate FaceSwap]: Video Face-Swap boshlandi...")
        
        with open(source_image_path, "rb") as s_img, open(target_video_path, "rb") as t_vid:
            output = replicate.run(
                "ddvinh1/video-faceswap-gpu:50a0a0018673852629578e627576326036b407e0dbd8cf8a0b5028296726dc5c",
                input={
                    "source_image": s_img,
                    "target_video": t_vid,
                    "enhance": True
                }
            )
            
        if output:
            url = str(output)
            print(f"[Replicate FaceSwap]: Tayyor: {url}")
            r = requests.get(url, timeout=180)
            if r.status_code == 200:
                with open(output_path, "wb") as f:
                    f.write(r.content)
                return True
    except Exception as e:
        print(f"[Replicate FaceSwap xatosi]: {e}")
        
    return False

def try_replicate_video(prompt, image_path=None, output_path=None):
    """Agar REPLICATE_API_TOKEN mavjud bo'lsa, Replicate orqali AI video yaratishga urinadi."""
    token = os.environ.get("REPLICATE_API_TOKEN", "") or REPLICATE_API_TOKEN
    if not token or not output_path:
        return False
        
    try:
        import replicate
        import requests
        print("🚀 [Replicate AI]: Video generatsiya boshlandi...")
        
        # Minimax Video-01
        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as img_file:
                output = replicate.run(
                    "minimax/video-01",
                    input={
                        "prompt": prompt or "High quality cinematic motion, highly detailed 4k, smooth cinematic video",
                        "first_frame_image": img_file,
                        "prompt_optimizer": True
                    }
                )
        else:
            output = replicate.run(
                "minimax/video-01",
                input={
                    "prompt": prompt or "Cinematic commercial video clip, ultra realistic, 4k",
                    "prompt_optimizer": True
                }
            )
            
        if output:
            url = str(output)
            print(f"[Replicate AI]: Video tayyor: {url}")
            r = requests.get(url, timeout=180)
            if r.status_code == 200:
                with open(output_path, "wb") as f:
                    f.write(r.content)
                return True
    except Exception as e:
        print(f"[Replicate AI] Ogohlantirish: {e}. Avtonom dvigatelga o'tilmoqda.")
        
    return False

def render_dynamic_video(fayl_nomi: str, mavzu: str, kadrlar: list, uploaded_images: list = None, vertical: bool = True, reference_video: str = None) -> str:
    """
    To'liq professional video rolik yaratuvchi dvigatel.
    1. Agar reference_video va rasm bo'lsa -> Replicate FaceSwap bajaradi.
    2. Agar matn/kadrlar bo'lsa -> Replicate Minimax AI video yaratadi.
    3. Agar Replicate offline bo'lsa -> Avtonom montaj dvigateli ishlaydi.
    """
    if not fayl_nomi.endswith('.mp4'):
        fayl_nomi = fayl_nomi.replace('.avi', '').replace('.mov', '') + '.mp4'
        
    output_path = os.path.join(BASE_DIR, fayl_nomi)
    first_img = uploaded_images[0] if (uploaded_images and len(uploaded_images) > 0) else None
    
    # 1. Face-Swap tekshirish
    if reference_video and os.path.exists(reference_video) and first_img:
        print("🎭 [Face-Swap]: Referans video va yuz rasmi orqali Face-Swap bajarilmoqda...")
        if try_replicate_faceswap(source_image_path=first_img, target_video_path=reference_video, output_path=output_path):
            return fayl_nomi
            
    # 2. Replicate AI Generatsiya sinab ko'ramiz
    prompt_full = f"{mavzu}. " + " ".join([k.get('vizual', '') or k.get('matn', '') for k in kadrlar if isinstance(k, dict)])
    if try_replicate_video(prompt_full, image_path=first_img, output_path=output_path):
        return fayl_nomi

    # 2. Avtonom Kinematografik Python Dvigateli
    print(f"[Video Asbob]: {fayl_nomi} yaratilmoqda (Avtonom HD Dvigatel)...")
    
    width = 720 if vertical else 1280
    height = 1280 if vertical else 720
    fps = 24
    seconds_per_scene = 4
    frames_per_scene = fps * seconds_per_scene
    
    # Kadrlar ro'yxatini to'g'irlash
    if not kadrlar or not isinstance(kadrlar, list):
        kadrlar = [
            {"sarlavha": mavzu or "Video Taqdimot", "matn": ""}
        ]
        
    # Yuklangan rasmlarni tayyorlash
    loaded_images = []
    if uploaded_images:
        for img_p in uploaded_images:
            if img_p and os.path.exists(img_p):
                try:
                    loaded_images.append(Image.open(img_p).convert("RGBA"))
                except Exception as e:
                    print("Rasm ochishda xato:", e)
                    
    font_badge = get_font(20, bold=True)
    font_title = get_font(30, bold=True)
    font_body = get_font(22, bold=False)
    
    writer = imageio.get_writer(
        output_path,
        fps=fps,
        codec='libx264',
        pixelformat='yuv420p',
        macro_block_size=1
    )
    
    total_scenes = len(kadrlar)
    scene_images = []
    
    # Har bir kadr uchun asosiy tasvirni tanlaymiz
    for idx, scene in enumerate(kadrlar):
        if loaded_images:
            # Agar foydalanuvchi rasm yuklagan bo'lsa, mosini olamiz
            img = loaded_images[idx % len(loaded_images)]
        else:
            img = None
        scene_images.append(img)
        
    for s_idx, scene in enumerate(kadrlar):
        s_title = scene.get('sarlavha', f"{s_idx+1}-Kadr") if isinstance(scene, dict) else f"{s_idx+1}-Kadr"
        s_text = scene.get('matn', '') if isinstance(scene, dict) else str(scene)
        base_img = scene_images[s_idx]
        
        for f in range(frames_per_scene):
            t = f / float(frames_per_scene) # 0.0 dan 1.0 gacha
            
            # 1. Asosiy fonni yaratamiz (Ken Burns zoom yoki gradient)
            frame_img = Image.new("RGBA", (width, height), (15, 23, 42, 255))
            
            if base_img:
                # Ken Burns Effect (Zoom 1.0x dan 1.15x gacha)
                scale = 1.0 + (0.15 * t)
                # Rasmni markazdan kesib, to'ldirish
                bw, bh = base_img.size
                aspect_target = width / float(height)
                aspect_img = bw / float(bh)
                
                if aspect_img > aspect_target:
                    crop_h = bh
                    crop_w = int(bh * aspect_target)
                else:
                    crop_w = bw
                    crop_h = int(bw / aspect_target)
                    
                # Kichik harakat (Pan)
                offset_x = int((bw - crop_w) * (0.5 + 0.2 * (t - 0.5)))
                offset_y = int((bh - crop_h) * 0.5)
                crop_box = (max(0, offset_x), max(0, offset_y), min(bw, offset_x + crop_w), min(bh, offset_y + crop_h))
                
                cropped = base_img.crop(crop_box)
                scaled_w = int(width * scale)
                scaled_h = int(height * scale)
                resized = cropped.resize((scaled_w, scaled_h), Image.Resampling.BILINEAR)
                
                # Canvas markaziga joylashtirish
                paste_x = (width - scaled_w) // 2
                paste_y = (height - scaled_h) // 2
                frame_img.paste(resized, (paste_x, paste_y))
            else:
                # Zamonaviy kinamatografik gradient fon
                draw_bg = ImageDraw.Draw(frame_img)
                c_top = (13, 20, 36)
                c_bot = (30, 41, 59)
                for y in range(height):
                    ratio = y / float(height)
                    r = int(c_top[0] + (c_bot[0] - c_top[0]) * ratio)
                    g = int(c_top[1] + (c_bot[1] - c_top[1]) * ratio)
                    b = int(c_top[2] + (c_bot[2] - c_top[2]) * ratio)
                    draw_bg.line([(0, y), (width, y)], fill=(r, g, b, 255))
                    
                # Dinamik harakatlanuvchi nur/chiziq
                glow_y = int(height * 0.4 + math.sin(t * math.pi * 2) * 50)
                draw_bg.ellipse([(width//2 - 200, glow_y - 100), (width//2 + 200, glow_y + 100)], fill=(37, 99, 235, 40))
                
            # 2. Qora yarim-shaffof gradient qoplama (pastki qism subtitrlar yaxshi o'qilishi uchun)
            overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            draw_ov = ImageDraw.Draw(overlay)
            
            # Yuqori qora gradient
            for y in range(0, int(height * 0.22)):
                alpha = int(180 * (1.0 - y / (height * 0.22)))
                draw_ov.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))
                
            # Pastki qora gradient
            sub_start = int(height * 0.55)
            for y in range(sub_start, height):
                alpha = int(220 * ((y - sub_start) / (height - sub_start)))
                draw_ov.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))
                
            frame_img = Image.alpha_composite(frame_img, overlay)
            draw = ImageDraw.Draw(frame_img)
            
            # 3. Yuqori studiya belgisi (Badge)
            badge_text = "🎬 TEMUR REJISSYOR • AI EXECUTIVE SUITE"
            draw.rectangle([(width//2 - 220, 30), (width//2 + 220, 68)], fill=(15, 23, 42, 210), outline=(59, 130, 246, 255), width=1)
            draw.text((width//2, 49), badge_text, fill=(226, 232, 240), font=font_badge, anchor="mm")
            
            # Kadr ko'rsatkichi
            scene_badge = f"KADR {s_idx + 1}/{total_scenes}"
            draw.rectangle([(width//2 - 60, 80), (width//2 + 60, 108)], fill=(37, 99, 235, 230))
            draw.text((width//2, 94), scene_badge, fill=(255, 255, 255), font=font_badge, anchor="mm")
            
            # 4. Kadr Sarlavhasi (O'rtada yoki pastki qism ustida)
            title_lines = wrap_text(s_title, font_title, width - 80, draw)
            start_y = int(height * 0.65)
            for l_idx, line in enumerate(title_lines):
                # Matn soyasi
                draw.text((width//2 + 2, start_y + l_idx * 38 + 2), line, fill=(0, 0, 0, 240), font=font_title, anchor="mm")
                draw.text((width//2, start_y + l_idx * 38), line, fill=(251, 191, 36), font=font_title, anchor="mm")
                
            # 5. Diktor nutqi / Subtitr (Pastda)
            sub_lines = wrap_text(s_text, font_body, width - 100, draw)
            body_start_y = start_y + len(title_lines) * 38 + 20
            
            # Subtitrlar foni (Pill box)
            if sub_lines:
                box_top = body_start_y - 12
                box_bottom = body_start_y + len(sub_lines) * 30 + 12
                draw.rounded_rectangle([(30, box_top), (width - 30, box_bottom)], radius=16, fill=(15, 23, 42, 220), outline=(71, 85, 105, 180), width=1)
                
                for l_idx, line in enumerate(sub_lines):
                    draw.text((width//2, body_start_y + l_idx * 30 + 5), line, fill=(241, 245, 249), font=font_body, anchor="mm")
                    
            # 6. Pastki progress bar (Qizil/ko'k chiziq)
            overall_progress = (s_idx * frames_per_scene + f) / float(total_scenes * frames_per_scene)
            draw.rectangle([(0, height - 8), (int(width * overall_progress), height)], fill=(37, 99, 235, 255))
            
            # RGBA dan RGB ga o'tkazib yozamiz
            final_frame = frame_img.convert("RGB")
            writer.append_data(np.array(final_frame))
            
    writer.close()
    print(f"[Video Asbob]: {fayl_nomi} muvaffaqiyatli saqlandi!")
    return fayl_nomi
