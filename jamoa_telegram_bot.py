import os
import threading
import glob
import json
import base64
try:
    import telebot
    from flask import Flask, render_template, request, jsonify, send_from_directory
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    import requests
except ImportError:
    print("Xatolik: Kutubxonalar yo'q. Terminalda yozing: pip install pyTelegramBotAPI flask openpyxl requests pillow imageio imageio-ffmpeg")
    exit(1)

from video_generator import render_dynamic_video

# XAVFSIZLIK: Kalitlarni serverdan olamiz
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")
OWNER_ID = os.environ.get("OWNER_ID", "")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.path.join(BASE_DIR, 'uploads')
os.makedirs(UPLOADS_DIR, exist_ok=True)

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, 'templates'),
    static_folder=os.path.join(BASE_DIR, 'static')
)

# =======================================================
# HAQIQIY EXCEL (.XLSX) YARATISH ASBOBI
# =======================================================
def excel_fayl_yaratish(fayl_nomi: str, ustunlar: list[str], qatorlar: list[list[str]]) -> str:
    """Haqiqiy professional Excel (.xlsx) fayl yaratadi."""
    if not fayl_nomi.endswith('.xlsx'):
        fayl_nomi = fayl_nomi.replace('.csv', '') + '.xlsx'
        
    fpath = os.path.join(BASE_DIR, fayl_nomi)
    print(f"[Excel Asbob]: {fayl_nomi} yaratilmoqda...")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Hisobot"
    
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    data_font = Font(name="Calibri", size=11)
    
    thin_border = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )
    
    ws.append(ustunlar)
    for col_num in range(1, len(ustunlar) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border
        
    for row_idx, row_data in enumerate(qatorlar, start=2):
        ws.append(row_data)
        for col_num in range(1, len(row_data) + 1):
            cell = ws.cell(row=row_idx, column=col_num)
            cell.font = data_font
            cell.border = thin_border
            if str(cell.value).replace(' ', '').replace(',', '').replace('.', '').isdigit():
                cell.alignment = Alignment(horizontal="right", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")
                
    for col in ws.columns:
        max_length = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_length + 4, 12)
        
    ws.row_dimensions[1].height = 26
    wb.save(fpath)
    return fayl_nomi

# =======================================================
# OPENROUTER AI ENGINE (MULTI-AGENT CORE & TOOLS)
# =======================================================
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "excel_fayl_yaratish",
            "description": "Faqat foydalanuvchi hisob-kitob, smeta, narxlar yoki jadval so'raganda chaqiriladi. Professional Excel (.xlsx) jadval faylini yaratish.",
            "parameters": {
                "type": "object",
                "properties": {
                    "fayl_nomi": {
                        "type": "string",
                        "description": "Fayl nomi (masalan: hisobot_narxlar.xlsx)"
                    },
                    "ustunlar": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Ustunlar nomlari ro'yxati (masalan: ['T/r', 'Kategoriya', 'Vazn', 'Narx', 'Izoh'])"
                    },
                    "qatorlar": {
                        "type": "array",
                        "items": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "description": "Ma'lumotlar qatorlari"
                    }
                },
                "required": ["fayl_nomi", "ustunlar", "qatorlar"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "video_rolik_yaratish",
            "description": "Faqat foydalanuvchi video, rolik, klip yoki animatsiya so'raganda chaqiriladi. Haqiqiy .mp4 video rolik yaratish.",
            "parameters": {
                "type": "object",
                "properties": {
                    "video_nomi": {
                        "type": "string",
                        "description": "Video fayl nomi (masalan: reklama_rolik.mp4)"
                    },
                    "mavzu": {
                        "type": "string",
                        "description": "Video rolikning asosiy g'oyasi yoki sarlavhasi"
                    },
                    "kadrlar": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "sarlavha": {"type": "string", "description": "Kadr sarlavhasi (masalan: 1-Kadr: Kirish)"},
                                "matn": {"type": "string", "description": "Kadr davomidagi ovozli diktor nutqi yoki subtitr matni"},
                                "vizual": {"type": "string", "description": "Kadrda nimalar aks etishi"}
                            },
                            "required": ["sarlavha", "matn"]
                        },
                        "description": "Videodagi kadrma-kadr sahnalar ro'yxati"
                    }
                },
                "required": ["video_nomi", "mavzu", "kadrlar"]
            }
        }
    }
]

SYSTEM_PROMPT = (
    "Sen Sardor — Professional Bosh Direktorsan (AI Executive Director). Sening qo'ling ostida 3 ta ishonchli mutaxassis xodim ishlaydi:\n"
    "1. Javohir — Bosh Iqtisodchi & Moliya tahlilchisi (Bozor narxlari, smeta va Excel .xlsx jadvallari ustasi).\n"
    "2. Madina — Bosh Kreativ Dizayner (Brending, matnlar, reklama va rasm promptlari ustasi).\n"
    "3. Temur — Bosh Video Rejissyor & IT (Video ssilkalarni tahlil qilish, kadrma-kadr video-hikoyalar va .mp4 video roliklar yaratish ustasi).\n\n"
    "ENG ASOSIY QONUN: FAQAT FOYDALANUVCHI SO'RAGAN NARSANI QIL!\n"
    "1. AGAR FOYDALANUVCHI EXCEL, JADVAL, NARXLAR, SMETA YOKI HISOBOT SO'RASA:\n"
    "   - FAQAT Javohir javob beradi va FAQAT 'excel_fayl_yaratish' funksiyasini chaqirib Excel (.xlsx) fayl yaratadi.\n"
    "   - Video UMUMAN qilinmaydi! Hech qanday video funksiyasini chaqirma!\n"
    "2. AGAR FOYDALANUVCHI VIDEO, ROLIK, KLIP YOKI VIDEO SSILKA ASOSIDA ROLIK SO'RASA:\n"
    "   - FAQAT Temur javob beradi va FAQAT 'video_rolik_yaratish' funksiyasini chaqirib .mp4 video fayl yaratadi.\n"
    "   - Excel UMUMAN qilinmaydi! Hech qanday excel funksiyasini chaqirma!\n"
    "3. AGAR FOYDALANUVCHI MATN, REKLAMA POSTI, MASLAHAT YOKI TUSHUNTIRISH SO'RASA:\n"
    "   - Hech qanday fayl yaratma! Faqat aniq, tushunarli va chiroyli matn bilan javob ber.\n"
    "4. BIR VAQTDA HAM EXCEL, HAM VIDEO BERISH QAT'IYAN TAQIQLANADI! Har bir so'rovga faqat 1 ta tegishli natija berilsin."
)

def ask_openrouter(messages, tools=None):
    """OpenRouter API orqali so'rov yuborish"""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://multi-agent-bot.onrender.com",
        "X-Title": "AI Executive Suite"
    }
    
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": messages,
        "max_tokens": 2500
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
        
    res = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=60
    )
    if res.status_code != 200:
        raise Exception(f"OpenRouter xatosi ({res.status_code}): {res.text}")
        
    return res.json()

def process_agent_request(user_text, target_agent='director', uploaded_images=None):
    """Foydalanuvchi topshirig'ini bajarib, faqat so'ralgan natijani qaytaradi"""
    if target_agent == 'finance':
        system_instruction = (
            "Sen Javohir — Bosh Iqtisodchi & Moliya tahlilchisisan. Foydalanuvchi narxlar, hisob-kitob yoki Excel jadval so'radi. "
            "Sening vazifang: 'excel_fayl_yaratish' funksiyasini chaqirib haqiqiy .xlsx Excel jadval yaratish! Hech qanday video qilma!"
        )
    elif target_agent == 'creative':
        system_instruction = (
            "Sen Madina — Bosh Kreativ Dizaynersan. Foydalanuvchi reklama matni yoki kreativ g'oya so'radi. "
            "Sening vazifang: Kuchli reklama matnlari va tavsiyalar berish. Hech qanday fayl yaratma."
        )
    elif target_agent == 'video':
        system_instruction = (
            "Sen Temur — Bosh Video Rejissyor & IT mutaxassisisan. Foydalanuvchi video rolik yoki animatsiya so'radi. "
            "Sening vazifang: 'video_rolik_yaratish' funksiyasini chaqirib haqiqiy .mp4 video rolik yaratish! Hech qanday Excel qilma!"
        )
    else:
        system_instruction = SYSTEM_PROMPT

    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": user_text}
    ]
    
    # So'rov yuborish
    resp = ask_openrouter(messages, tools=TOOLS_SCHEMA)
    choice = resp['choices'][0]
    message_obj = choice['message']
    
    tool_calls = message_obj.get('tool_calls')
    created_excel = None
    created_video = None
    
    if tool_calls:
        tool_responses = []
        for tc in tool_calls:
            t_name = tc['function']['name']
            t_id = tc['id']
            try:
                args = json.loads(tc['function']['arguments'])
            except Exception:
                args = {}
                
            # FAQAT BITTA ASOSIY ASBOB ISHLATILADI:
            if t_name == 'excel_fayl_yaratish' and not created_video:
                try:
                    f_res = excel_fayl_yaratish(
                        args.get('fayl_nomi', 'hisobot.xlsx'),
                        args.get('ustunlar', []),
                        args.get('qatorlar', [])
                    )
                    created_excel = f_res
                    created_video = None  # Video bo'lmasligi shart!
                    content_str = f"Excel fayli '{f_res}' yaratildi."
                except Exception as e:
                    content_str = f"Excel xatosi: {e}"
                tool_responses.append({
                    "role": "tool",
                    "tool_call_id": t_id,
                    "name": t_name,
                    "content": content_str
                })
            elif t_name == 'video_rolik_yaratish' and not created_excel:
                try:
                    v_res = render_dynamic_video(
                        args.get('video_nomi', 'rolik.mp4'),
                        args.get('mavzu', 'Video taqdimot'),
                        args.get('kadrlar', []),
                        uploaded_images=uploaded_images
                    )
                    created_video = v_res
                    created_excel = None  # Excel bo'lmasligi shart!
                    content_str = f"Video fayli '{v_res}' yaratildi."
                except Exception as e:
                    content_str = f"Video xatosi: {e}"
                tool_responses.append({
                    "role": "tool",
                    "tool_call_id": t_id,
                    "name": t_name,
                    "content": content_str
                })
                
        if tool_responses:
            messages.append(message_obj)
            messages.extend(tool_responses)
            final_resp = ask_openrouter(messages)
            final_text = final_resp['choices'][0]['message'].get('content', '')
        else:
            final_text = message_obj.get('content', '')
    else:
        final_text = message_obj.get('content', '')

    # Qo'shimcha nazorat: agar foydalanuvchi aniq so'ragan bo'lsa-yu, ikkalasi aralashsa
    if created_excel and created_video:
        low_t = user_text.lower()
        if any(w in low_t for w in ['video', 'rolik', 'klip', 'ssilka', 'silka']):
            created_excel = None
        else:
            created_video = None

    if created_excel:
        ep = os.path.join(BASE_DIR, created_excel)
        if not os.path.exists(ep) or os.path.getsize(ep) < 500:
            created_excel = None

    if created_video:
        vp = os.path.join(BASE_DIR, created_video)
        if not os.path.exists(vp) or os.path.getsize(vp) < 1000:
            created_video = None

    return final_text, created_excel, created_video

# =======================================================
# FLASK WEB DASHBOARD & REST API
# =======================================================
@app.route('/')
def dashboard():
    return render_template('index.html')

@app.route('/api/task', methods=['POST'])
def api_task():
    uploaded_images = []
    
    if request.files:
        task_text = request.form.get('task', '').strip()
        target_agent = request.form.get('target_agent', 'director')
        
        for file in request.files.getlist('files'):
            if file and file.filename:
                safe_name = os.path.basename(file.filename)
                save_path = os.path.join(UPLOADS_DIR, safe_name)
                file.save(save_path)
                uploaded_images.append(save_path)
    else:
        data = request.json or {}
        task_text = data.get('task', '').strip()
        target_agent = data.get('target_agent', 'director')
        
    if not task_text and not uploaded_images:
        return jsonify({'status': 'error', 'error': 'Topshiriq matni yoki rasm kiritilmadi'}), 400
        
    try:
        report, excel_file, video_file = process_agent_request(
            task_text,
            target_agent=target_agent,
            uploaded_images=uploaded_images
        )
        return jsonify({
            'status': 'success',
            'report': report,
            'excel_file': excel_file,
            'video_file': video_file
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/voice', methods=['POST'])
def api_voice():
    try:
        report, excel_file, video_file = process_agent_request(
            "Ovozli topshiriq bo'yicha to'liq hisobot tayyorlab ber."
        )
        return jsonify({
            'status': 'success',
            'report': report,
            'excel_file': excel_file,
            'video_file': video_file
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/files', methods=['GET'])
def api_files():
    xlsx_files = [os.path.basename(f) for f in glob.glob(os.path.join(BASE_DIR, "*.xlsx")) if os.path.getsize(f) > 500]
    mp4_files = [os.path.basename(f) for f in glob.glob(os.path.join(BASE_DIR, "*.mp4")) if os.path.getsize(f) > 1000]
    return jsonify({
        'xlsx_files': xlsx_files,
        'mp4_files': mp4_files,
        'files': xlsx_files + mp4_files
    })

@app.route('/api/download/<filename>')
def api_download(filename):
    fpath = os.path.join(BASE_DIR, filename)
    if os.path.exists(fpath):
        is_video = filename.endswith('.mp4')
        return send_from_directory(BASE_DIR, filename, as_attachment=not is_video)
        
    fpath_up = os.path.join(UPLOADS_DIR, filename)
    if os.path.exists(fpath_up):
        is_video = filename.endswith('.mp4')
        return send_from_directory(UPLOADS_DIR, filename, as_attachment=not is_video)
        
    return "Fayl topilmadi", 404

def run_web_server():
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# =======================================================
# TELEGRAM BOT TIZIMI
# =======================================================
def run_telegram_bot():
    if not TELEGRAM_BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN kiritilmagan. Bot ishga tushmadi.")
        return
        
    bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

    def check_access(message):
        if OWNER_ID and str(message.chat.id) != str(OWNER_ID):
            bot.reply_to(message, "⛔ Kechirasiz! Bu shaxsiy AI Agent boti. Undan faqat uning haqiqiy egasi foydalana oladi.")
            return False
        return True

    @bot.message_handler(commands=['start', 'myid'])
    def send_welcome(message):
        if not check_access(message):
            return
        bot.reply_to(
            message,
            f"Salom hurmatli rahbar! Men sizning Bosh Direktoringiz Sardorman.\n\n"
            f"🆔 Sizning Telegram ID: `{message.chat.id}`\n\n"
            f"💼 Jamoamiz siz qanday topshiriq bersangiz, aynan o'sha formatda bajaradi:\n"
            f"• 📊 Jadval, narx yoki hisobot so'rasangiz -> FAQAT Excel (.xlsx) jadvali\n"
            f"• 🎬 Video, rolik yoki klip so'rasangiz -> FAQAT Video (.mp4) roligi\n"
            f"• ✍️ Maslahat yoki matn so'rasangiz -> FAQAT professional matn\n\n"
            f"Topshirig'ingizni bering yoki rasm yuboring!",
            parse_mode='Markdown'
        )

    @bot.message_handler(content_types=['text'])
    def handle_text(message):
        if not check_access(message):
            return
        bot.send_chat_action(message.chat.id, 'typing')
        try:
            report, excel_file, video_file = process_agent_request(message.text)
            bot.send_message(message.chat.id, report)
            
            # FAQAT SO'RALGAN FAYL YUBORILADI (Ikkisi birga yuborilmaydi)
            if excel_file:
                fpath = os.path.join(BASE_DIR, excel_file)
                if os.path.exists(fpath) and os.path.getsize(fpath) > 500:
                    with open(fpath, "rb") as doc:
                        bot.send_document(message.chat.id, doc, caption="📊 Siz so'ragan tayyor Excel hisoboti")
            elif video_file:
                vpath = os.path.join(BASE_DIR, video_file)
                if os.path.exists(vpath) and os.path.getsize(vpath) > 1000:
                    with open(vpath, "rb") as vid:
                        bot.send_video(message.chat.id, vid, caption="🎬 Siz so'ragan tayyor video rolik (.mp4)")
        except Exception as e:
            bot.reply_to(message, f"Xatolik yuz berdi: {e}")

    media_groups_cache = {}
    media_groups_lock = threading.Lock()

    def process_media_group(mg_id):
        with media_groups_lock:
            data = media_groups_cache.pop(mg_id, None)
        if not data:
            return
            
        chat_id = data['chat_id']
        photos = data['photos']
        caption = data['caption']
        bot.send_chat_action(chat_id, 'typing')
        
        low_c = caption.lower()
        if any(w in low_c for w in ['video', 'rolik', 'klip', 'ssilka', 'silka', 'harakatlantir']):
            target_agent = 'video'
            prompt_text = caption or "Ushbu rasmlar asosida video rolik yaratib ber."
        elif any(w in low_c for w in ['excel', 'jadval', 'narx', 'narxlari', 'smeta', 'hisob', 'hisobot']):
            target_agent = 'finance'
            prompt_text = caption or "Ushbu rasmlar bo'yicha narxlar va hisob-kitob qilib Excel jadval tayyorla."
        else:
            target_agent = 'director'
            prompt_text = caption or f"Ushbu biriktirilgan {len(photos)} ta rasmni tahlil qilib to'liq ma'lumot bering."

        try:
            report, excel_file, video_file = process_agent_request(
                prompt_text,
                target_agent=target_agent,
                uploaded_images=photos
            )
            bot.send_message(chat_id, report)
            if excel_file:
                fpath = os.path.join(BASE_DIR, excel_file)
                if os.path.exists(fpath) and os.path.getsize(fpath) > 500:
                    with open(fpath, "rb") as doc:
                        bot.send_document(chat_id, doc, caption="📊 Siz so'ragan tayyor Excel hisoboti")
            elif video_file:
                vpath = os.path.join(BASE_DIR, video_file)
                if os.path.exists(vpath) and os.path.getsize(vpath) > 1000:
                    with open(vpath, "rb") as vid:
                        bot.send_video(chat_id, vid, caption="🎬 Rasmlar asosida tayyorlangan video rolik (.mp4)")
        except Exception as e:
            bot.send_message(chat_id, f"Rasmlarni tahlil qilishda xatolik: {e}")

    @bot.message_handler(content_types=['photo'])
    def handle_photo(message):
        if not check_access(message):
            return
        try:
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded = bot.download_file(file_info.file_path)
            
            photo_name = f"tg_photo_{message.photo[-1].file_id[:8]}_{os.urandom(2).hex()}.jpg"
            photo_path = os.path.join(UPLOADS_DIR, photo_name)
            with open(photo_path, 'wb') as new_f:
                new_f.write(downloaded)
                
            mg_id = getattr(message, 'media_group_id', None)
            if mg_id:
                with media_groups_lock:
                    if mg_id not in media_groups_cache:
                        media_groups_cache[mg_id] = {
                            'chat_id': message.chat.id,
                            'photos': [photo_path],
                            'caption': message.caption or '',
                            'timer': threading.Timer(1.5, process_media_group, args=[mg_id])
                        }
                        media_groups_cache[mg_id]['timer'].start()
                    else:
                        media_groups_cache[mg_id]['photos'].append(photo_path)
                        if message.caption:
                            media_groups_cache[mg_id]['caption'] = message.caption
                        media_groups_cache[mg_id]['timer'].cancel()
                        media_groups_cache[mg_id]['timer'] = threading.Timer(1.5, process_media_group, args=[mg_id])
                        media_groups_cache[mg_id]['timer'].start()
                return

            bot.send_chat_action(message.chat.id, 'typing')
            caption = message.caption or ""
            low_c = caption.lower()
            if any(w in low_c for w in ['video', 'rolik', 'klip', 'ssilka', 'silka', 'harakatlantir']):
                target_agent = 'video'
                prompt_text = caption or "Ushbu rasm asosida video rolik yaratib ber."
            elif any(w in low_c for w in ['excel', 'jadval', 'narx', 'narxlari', 'smeta', 'hisob', 'hisobot']):
                target_agent = 'finance'
                prompt_text = caption or "Ushbu rasm bo'yicha narxlar va hisob-kitob qilib Excel jadval tayyorla."
            else:
                target_agent = 'director'
                prompt_text = caption or "Ushbu rasmni tahlil qilib to'liq ma'lumot bering."

            report, excel_file, video_file = process_agent_request(
                prompt_text,
                target_agent=target_agent,
                uploaded_images=[photo_path]
            )
            bot.send_message(message.chat.id, report)
            if excel_file:
                fpath = os.path.join(BASE_DIR, excel_file)
                if os.path.exists(fpath) and os.path.getsize(fpath) > 500:
                    with open(fpath, "rb") as doc:
                        bot.send_document(message.chat.id, doc, caption="📊 Siz so'ragan tayyor Excel hisoboti")
            elif video_file:
                vpath = os.path.join(BASE_DIR, video_file)
                if os.path.exists(vpath) and os.path.getsize(vpath) > 1000:
                    with open(vpath, "rb") as vid:
                        bot.send_video(message.chat.id, vid, caption="🎬 Rasm asosida tayyorlangan video rolik (.mp4)")
        except Exception as e:
            bot.reply_to(message, f"Rasm tahlilida xatolik: {e}")

    @bot.message_handler(content_types=['video'])
    def handle_video(message):
        if not check_access(message):
            return
        bot.send_chat_action(message.chat.id, 'typing')
        try:
            file_info = bot.get_file(message.video.file_id)
            downloaded = bot.download_file(file_info.file_path)
            
            vid_name = f"tg_vid_{message.video.file_id[:8]}.mp4"
            vid_path = os.path.join(UPLOADS_DIR, vid_name)
            with open(vid_path, 'wb') as new_f:
                new_f.write(downloaded)
                
            caption = message.caption or "Ushbu videoni tahlil qilib to'liq ma'lumot bering."
            report, excel_file, video_file = process_agent_request(
                caption,
                target_agent='video',
                uploaded_images=[vid_path]
            )
            bot.send_message(message.chat.id, report)
            if excel_file:
                fpath = os.path.join(BASE_DIR, excel_file)
                if os.path.exists(fpath) and os.path.getsize(fpath) > 500:
                    with open(fpath, "rb") as doc:
                        bot.send_document(message.chat.id, doc, caption="📊 Hisobot (.xlsx)")
            elif video_file:
                vpath = os.path.join(BASE_DIR, video_file)
                if os.path.exists(vpath) and os.path.getsize(vpath) > 1000:
                    with open(vpath, "rb") as vid:
                        bot.send_video(message.chat.id, vid, caption="🎬 Tayyor video rolik (.mp4)")
        except Exception as e:
            bot.reply_to(message, f"Video tahlilida xatolik: {e}")

    @bot.message_handler(content_types=['voice'])
    def handle_voice(message):
        if not check_access(message):
            return
        bot.send_chat_action(message.chat.id, 'typing')
        try:
            bot.reply_to(message, "Ovozli xabar qabul qilindi. Topshiriq bajarilmoqda...")
            report, excel_file, video_file = process_agent_request(
                "Ovozli topshiriq: Iltimos, topshiriq bo'yicha to'liq hisobot bering."
            )
            bot.send_message(message.chat.id, report)
            if excel_file:
                fpath = os.path.join(BASE_DIR, excel_file)
                if os.path.exists(fpath) and os.path.getsize(fpath) > 500:
                    with open(fpath, "rb") as doc:
                        bot.send_document(message.chat.id, doc, caption="📊 Siz so'ragan tayyor Excel hisoboti")
            elif video_file:
                vpath = os.path.join(BASE_DIR, video_file)
                if os.path.exists(vpath) and os.path.getsize(vpath) > 1000:
                    with open(vpath, "rb") as vid:
                        bot.send_video(message.chat.id, vid, caption="🎬 Siz so'ragan tayyor video rolik (.mp4)")
        except Exception as e:
            bot.reply_to(message, f"Xatolik yuz berdi: {e}")

    print("Telegram bot ishga tushdi...")
    bot.infinity_polling()

if __name__ == "__main__":
    t = threading.Thread(target=run_web_server, daemon=True)
    t.start()
    run_telegram_bot()
