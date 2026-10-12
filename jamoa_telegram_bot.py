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
            "description": "Professional Excel (.xlsx) jadval faylini yaratish",
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
            "description": "Haqiqiy .mp4 formatdagi video rolik yaratish (Replicate AI yoki avtonom HD video dvigateli yordamida).",
            "parameters": {
                "type": "object",
                "properties": {
                    "video_nomi": {
                        "type": "string",
                        "description": "Video fayl nomi (masalan: labo_reklama.mp4 yoki hikoya_rolik.mp4)"
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
                                "sarlavha": {"type": "string", "description": "Kadr sarlavhasi (masalan: 1-Kadr: Bosh qahramon kirishi)"},
                                "matn": {"type": "string", "description": "Kadr davomidagi ovozli diktor nutqi yoki subtitr matni"},
                                "vizual": {"type": "string", "description": "Kadrda nimalar aks etishi (kamera harakati, mashina, qahramon)"}
                            },
                            "required": ["sarlavha", "matn"]
                        },
                        "description": "Videodagi kadrma-kadr sahnalar ro'yxati (har bir kadr 4 soniya)"
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
    "3. Temur — Bosh Video Rejissyor & IT (Video ssilkalarni tahlil qilish, kadrma-kadr video-hikoyalar va ALBATTA 'video_rolik_yaratish' orqali HAQIQIY .mp4 video roliklar yaratish ustasi).\n\n"
    "QAT'IY QOIDALAR:\n"
    "1. FAQAT TEGISHLI XODIM JAVOB BERSIN: Agar mavzu video yoki rasm haqida bo'lsa, Javohir (Moliya) aralashmasin va 'men hech narsa qilmadim' deb yozma! Faqat topshiriqqa javobgar mutaxassis (Temur yoki Madina) to'liq natijani taqdim etsin!\n"
    "2. VIDEO, SSILKA VA RASMLAR BERILGANDA: Temur darhol videoni yoki mavzuni tahlil qilsin, foydalanuvchi bergan rasm yoki talablarni inobatga olsin va ALBATTA 'video_rolik_yaratish' asbobini chaqirib HAQIQIY .mp4 video fayl yaratsin! Hech qachon faqat matn yozib to'xtab qolma, har doim video_rolik_yaratish orqali haqiqiy rolikni taqdim et!\n"
    "3. EXCEL VA JADVALLAR: Agar hisobot, narxlar ro'yxati yoki jadval so'ralsa, Javohir ALBATTA 'excel_fayl_yaratish' funksiyasini chaqirib haqiqiy .xlsx fayl yaratsin!\n"
    "4. Hech qachon sayoz, 1 qatorli yoki 'hech nima qilmadi' degan javob berma! Har bir topshiriqqa to'liq, professional va mukammal yondash."
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
    """Foydalanuvchi topshirig'ini bajarib, matn, Excel fayli va Video faylini qaytaradi"""
    if target_agent == 'finance':
        system_instruction = (
            "Sen Javohir — Bosh Iqtisodchi & Moliya tahlilchisisan. Rahbar to'g'ridan-to'g'ri sening xonangga kirib topshiriq berdi. "
            "Sening ishingni Bosh Direktor Sardor sinchiklab kuzatib turibdi.\n"
            "Vazifang: Aniq bozor narxlari, tahlil, smeta va ALBATTA 'excel_fayl_yaratish' funksiyasini chaqirib haqiqiy .xlsx Excel jadval yaratish! "
            "Javobingni donama-dona tartibda va chiroyli emojilar bilan ber."
        )
    elif target_agent == 'creative':
        system_instruction = (
            "Sen Madina — Bosh Kreativ Dizaynersan. Rahbar to'g'ridan-to'g'ri sening xonangga kirib topshiriq berdi. "
            "Sening ishingni Bosh Direktor Sardor kuzatib turibdi.\n"
            "Vazifang: Kuchli reklama matnlari, brending konsepsiyalari va Midjourney/Flux uchun fotorealistik vizual promptlarni donama-dona qilib berish."
        )
    elif target_agent == 'video':
        system_instruction = (
            "Sen Temur — Bosh Video Rejissyor & IT mutaxassisisan. Rahbar to'g'ridan-to'g'ri sening xonangga kirib topshiriq berdi. "
            "Sening ishingni Bosh Direktor Sardor kuzatib turibdi.\n"
            "Vazifang: Video ssilkalarni tahlil qilish, kadrlar ssenariysini tuzish va "
            "ALBATTA 'video_rolik_yaratish' funksiyasini chaqirib HAQIQIY .mp4 video rolikni yaratish! "
            "Foydalanuvchi yuklagan rasmlarni (qahramon, mahsulot, mashina) videoga kiritib, unga yuklab olish uchun tayyor video berishing shart!"
        )
    else:
        system_instruction = SYSTEM_PROMPT

    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": user_text}
    ]
    
    old_xlsx = set(glob.glob(os.path.join(BASE_DIR, "*.xlsx")))
    old_mp4 = set(glob.glob(os.path.join(BASE_DIR, "*.mp4")))
    
    # 1. So'rov yuborish
    resp = ask_openrouter(messages, tools=TOOLS_SCHEMA)
    choice = resp['choices'][0]
    message_obj = choice['message']
    
    tool_calls = message_obj.get('tool_calls')
    created_excel = None
    created_video = None
    
    # 2. Agar model vositani chaqirgan bo'lsa
    if tool_calls:
        tool_responses = []
        for tc in tool_calls:
            t_name = tc['function']['name']
            t_id = tc['id']
            try:
                args = json.loads(tc['function']['arguments'])
            except Exception:
                args = {}
                
            if t_name == 'excel_fayl_yaratish':
                try:
                    f_res = excel_fayl_yaratish(
                        args.get('fayl_nomi', 'hisobot.xlsx'),
                        args.get('ustunlar', []),
                        args.get('qatorlar', [])
                    )
                    content_str = f"Excel fayli '{f_res}' muvaffaqiyatli yaratildi."
                except Exception as e:
                    content_str = f"Excel yaratishda xato: {e}"
                tool_responses.append({
                    "role": "tool",
                    "tool_call_id": t_id,
                    "name": t_name,
                    "content": content_str
                })
            elif t_name == 'video_rolik_yaratish':
                try:
                    v_res = render_dynamic_video(
                        args.get('video_nomi', 'rolik.mp4'),
                        args.get('mavzu', 'Video taqdimot'),
                        args.get('kadrlar', []),
                        uploaded_images=uploaded_images
                    )
                    content_str = f"Haqiqiy MP4 video rolik '{v_res}' muvaffaqiyatli yaratildi va saqlandi."
                except Exception as e:
                    content_str = f"Video yaratishda xato: {e}"
                tool_responses.append({
                    "role": "tool",
                    "tool_call_id": t_id,
                    "name": t_name,
                    "content": content_str
                })
                
        # Modelga natijalarni bildirib, yakuniy xulosani olamiz
        messages.append(message_obj)
        messages.extend(tool_responses)
        final_resp = ask_openrouter(messages)
        final_text = final_resp['choices'][0]['message'].get('content', '')
    else:
        final_text = message_obj.get('content', '')
        
        # Maxsus avtomatik kafolat: Agar video so'ralgan bo'lsa yoki Temur xonasida bo'lsa,
        # lekin model tool chaqirishni unutgan bo'lsa, avtomatik tarzda video_rolik_yaratish ishga tushadi!
        low_t = user_text.lower()
        if target_agent == 'video' or 'video' in low_t or 'rolik' in low_t or 'ssilka' in low_t or 'silka' in low_t or uploaded_images:
            try:
                auto_video_name = f"video_{len(old_mp4)+1}.mp4"
                print(f"[Avtomatik Video]: Video talab etilganligi uchun '{auto_video_name}' yaratilmoqda...")
                auto_kadrlar = [
                    {"sarlavha": "1-Kadr: Kirish & Tavsif", "matn": user_text[:100] if user_text else "Yangi video loyiha"},
                    {"sarlavha": "2-Kadr: Asosiy Tafsilot", "matn": "Qahramon va mahsulot namoyishi, to'liq ma'lumotlar"},
                    {"sarlavha": "3-Kadr: Yakuniy Xulosa", "matn": "Muvaffaqiyatli yakun va hamkorlik uchun murojaat"}
                ]
                render_dynamic_video(auto_video_name, user_text or "Video Rolik", auto_kadrlar, uploaded_images=uploaded_images)
            except Exception as e:
                print("Avtomatik video yaratishda xato:", e)

    # Yangi paydo bo'lgan fayllarni aniqlaymiz
    new_xlsx = set(glob.glob(os.path.join(BASE_DIR, "*.xlsx"))) - old_xlsx
    if new_xlsx:
        created_excel = os.path.basename(list(new_xlsx)[0])
        
    new_mp4 = set(glob.glob(os.path.join(BASE_DIR, "*.mp4"))) - old_mp4
    if new_mp4:
        created_video = os.path.basename(list(new_mp4)[0])
        
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
    
    # 1. Multipart/form-data orqali kelgan so'rov (fayllar bilan birga)
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
        # 2. JSON orqali kelgan so'rov
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
            "Ovozli buyruq: Iltimos, so'nggi xarajatlar va bozor narxlari bo'yicha to'liq hisobot tayyorlab ber."
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
    xlsx_files = [os.path.basename(f) for f in glob.glob(os.path.join(BASE_DIR, "*.xlsx"))]
    mp4_files = [os.path.basename(f) for f in glob.glob(os.path.join(BASE_DIR, "*.mp4"))]
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
            f"💼 Jamoamiz imkoniyatlari:\n"
            f"• 📊 Javohir: Bozor narxlari va professional Excel (.xlsx) hisobotlari\n"
            f"• 🎨 Madina: Reklama matnlari va fotorealistik Midjourney promptlar\n"
            f"• 🎬 Temur: Video ssilka va rasmlar asosida haqiqiy MP4 video roliklar yaratish!\n\n"
            f"Menga xohlagan topshiriqni bering, yoki rasm/ssilka yuboring!",
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
            
            if excel_file:
                fpath = os.path.join(BASE_DIR, excel_file)
                if os.path.exists(fpath):
                    with open(fpath, "rb") as doc:
                        bot.send_document(message.chat.id, doc, caption="📊 Siz so'ragan tayyor Excel hisoboti")
                        
            if video_file:
                vpath = os.path.join(BASE_DIR, video_file)
                if os.path.exists(vpath):
                    with open(vpath, "rb") as vid:
                        bot.send_video(message.chat.id, vid, caption="🎬 Temur: Siz so'ragan tayyor video rolik (.mp4)")
        except Exception as e:
            bot.reply_to(message, f"Xatolik yuz berdi: {e}")

    @bot.message_handler(content_types=['photo'])
    def handle_photo(message):
        if not check_access(message):
            return
        bot.send_chat_action(message.chat.id, 'upload_video')
        try:
            # Eng yuqori sifatli fotosuratni yuklab olamiz
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded = bot.download_file(file_info.file_path)
            
            photo_name = f"tg_photo_{message.photo[-1].file_id[:8]}.jpg"
            photo_path = os.path.join(UPLOADS_DIR, photo_name)
            with open(photo_path, 'wb') as new_f:
                new_f.write(downloaded)
                
            caption = message.caption or "Ushbu rasm asosida qiziqarli video rolik ssenariysi va tayyor MP4 video yaratib ber."
            prompt_with_photo = f"{caption} (Foydalanuvchi qahramon/mahsulot rasmini yubordi: {photo_name})"
            
            report, excel_file, video_file = process_agent_request(
                prompt_with_photo,
                target_agent='video',
                uploaded_images=[photo_path]
            )
            bot.send_message(message.chat.id, report)
            
            if video_file:
                vpath = os.path.join(BASE_DIR, video_file)
                if os.path.exists(vpath):
                    with open(vpath, "rb") as vid:
                        bot.send_video(message.chat.id, vid, caption="🎬 Temur: Rasm asosida tayyorlangan video rolik!")
        except Exception as e:
            bot.reply_to(message, f"Rasm tahlilida xatolik: {e}")

    @bot.message_handler(content_types=['voice'])
    def handle_voice(message):
        if not check_access(message):
            return
        bot.send_chat_action(message.chat.id, 'typing')
        try:
            bot.reply_to(message, "Ovozli xabar qabul qilindi. Topshiriq bajarilmoqda...")
            report, excel_file, video_file = process_agent_request(
                "Ovozli topshiriq: Iltimos, batafsil hisobot tayyorlab ber va kerak bo'lsa Excel jadval yoki video yarat."
            )
            bot.send_message(message.chat.id, report)
            if excel_file:
                fpath = os.path.join(BASE_DIR, excel_file)
                if os.path.exists(fpath):
                    with open(fpath, "rb") as doc:
                        bot.send_document(message.chat.id, doc, caption="📊 Siz so'ragan tayyor Excel hisoboti")
            if video_file:
                vpath = os.path.join(BASE_DIR, video_file)
                if os.path.exists(vpath):
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
