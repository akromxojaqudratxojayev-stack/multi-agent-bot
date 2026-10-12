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
    print("Xatolik: Kutubxonalar yo'q. Terminalda yozing: pip install pyTelegramBotAPI flask openpyxl requests")
    exit(1)

# XAVFSIZLIK: Kalitlarni serverdan olamiz
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")
OWNER_ID = os.environ.get("OWNER_ID", "")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
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
    print(f"📊 [Excel Asbob]: {fayl_nomi} yaratilmoqda...")
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
# OPENROUTER AI ENGINE (MULTI-AGENT CORE)
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
                        "description": "Fayl nomi (masalan: qoramol_narxlari.xlsx)"
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
    }
]

SYSTEM_PROMPT = (
    "Sen professional Bosh Direktorsan (Executive AI Director). Sening qo'lingda Moliya, Kreativ, Video va Dasturchilar jamoasi bor.\n"
    "QAT'IY QOIDALAR:\n"
    "1. Javoblaringni hech qachon matn ichida aralashtirib yuborma! Xuddi rasmiy tender yoki biznes hisobotdek DONAMA-DONA, har bir ma'lumotni alohida qatorda ko'rsat.\n"
    "2. Emojilardan tartibli va chiroyli foydalan (📌 Mavzu/Lot, 🏛️ Tashkilot/Manba, 💰 Narx/Byudjet, 📦 Vazn/Miqdor, 🚚 Muddat, 📅 Sana, 📝 Izoh, 🔹 Bandlar).\n"
    "3. Agar foydalanuvchi hisobot, ro'yxat, narxlar, jadval so'rasa yoki Excel haqida gapirsa, ALBATTA 'excel_fayl_yaratish' funksiyasini chaqir!\n"
    "4. Agar oddiy salom-alik bo'lsa, xodimlarni bezovta qilma, o'zing qisqa samimiy javob ber."
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

def process_agent_request(user_text):
    """Foydalanuvchi topshirig'ini bajarib, matn va yaratilgan Excel faylini qaytaradi"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_text}
    ]
    
    old_files = set(glob.glob(os.path.join(BASE_DIR, "*.xlsx")))
    
    # 1. So'rov yuborish
    resp = ask_openrouter(messages, tools=TOOLS_SCHEMA)
    choice = resp['choices'][0]
    message_obj = choice['message']
    
    tool_calls = message_obj.get('tool_calls')
    created_excel = None
    
    # 2. Agar model Excel yaratish vositasini chaqirgan bo'lsa
    if tool_calls:
        for tc in tool_calls:
            if tc['function']['name'] == 'excel_fayl_yaratish':
                try:
                    args = json.loads(tc['function']['arguments'])
                    excel_fayl_yaratish(
                        args.get('fayl_nomi', 'hisobot.xlsx'),
                        args.get('ustunlar', []),
                        args.get('qatorlar', [])
                    )
                except Exception as e:
                    print("Excel yaratishda xato:", e)
                    
        # Modelga natijani bildirib, yakuniy xisobotni olamiz
        messages.append(message_obj)
        messages.append({
            "role": "tool",
            "tool_call_id": tool_calls[0]['id'],
            "name": "excel_fayl_yaratish",
            "content": "Excel fayl muvaffaqiyatli yaratildi va saqlandi."
        })
        final_resp = ask_openrouter(messages)
        final_text = final_resp['choices'][0]['message'].get('content', '')
    else:
        final_text = message_obj.get('content', '')
        
    # Yangi paydo bo'lgan faylni aniqlaymiz
    new_files = set(glob.glob(os.path.join(BASE_DIR, "*.xlsx"))) - old_files
    if new_files:
        created_excel = os.path.basename(list(new_files)[0])
        
    return final_text, created_excel

# =======================================================
# FLASK WEB DASHBOARD & REST API
# =======================================================
@app.route('/')
def dashboard():
    return render_template('index.html')

@app.route('/api/task', methods=['POST'])
def api_task():
    data = request.json or {}
    task_text = data.get('task', '').strip()
    if not task_text:
        return jsonify({'status': 'error', 'error': 'Topshiriq matni kiritilmadi'}), 400
        
    try:
        report, excel_file = process_agent_request(task_text)
        return jsonify({
            'status': 'success',
            'report': report,
            'excel_file': excel_file
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/voice', methods=['POST'])
def api_voice():
    # Dashboarddan ovoz kelganda
    try:
        # Hozircha ovozli buyruq bo'yicha bildirishnoma
        report, excel_file = process_agent_request("Ovozli buyruq: Iltimos, so'nggi xarajatlar va bozor narxlari bo'yicha to'liq hisobot tayyorlab, Excel faylini ber.")
        return jsonify({
            'status': 'success',
            'report': report,
            'excel_file': excel_file
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/files', methods=['GET'])
def api_files():
    files = [os.path.basename(f) for f in glob.glob(os.path.join(BASE_DIR, "*.xlsx"))]
    return jsonify({'files': files})

@app.route('/api/download/<filename>')
def api_download(filename):
    return send_from_directory(BASE_DIR, filename, as_attachment=True)

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
            f"Salom hurmatli rahbar! Men sizning Bosh Direktoringizman (OpenRouter AI dvigatelida).\n\n"
            f"🆔 Sizning Telegram ID: `{message.chat.id}`\n\n"
            f"Menga xohlagan topshiriqni bering, barcha ma'lumotlarni donama-dona qilib tahlil qilib, kerak bo'lsa tayyor Excel (.xlsx) faylini ham yuklab beraman! 📊",
            parse_mode='Markdown'
        )

    @bot.message_handler(content_types=['text'])
    def handle_text(message):
        if not check_access(message):
            return
        bot.send_chat_action(message.chat.id, 'typing')
        try:
            report, excel_file = process_agent_request(message.text)
            bot.send_message(message.chat.id, report)
            
            if excel_file:
                fpath = os.path.join(BASE_DIR, excel_file)
                if os.path.exists(fpath):
                    with open(fpath, "rb") as doc:
                        bot.send_document(message.chat.id, doc, caption="📥 Siz so'ragan tayyor Excel hisoboti")
        except Exception as e:
            bot.reply_to(message, f"Xatolik yuz berdi: {e}")

    @bot.message_handler(content_types=['voice'])
    def handle_voice(message):
        if not check_access(message):
            return
        bot.send_chat_action(message.chat.id, 'typing')
        try:
            bot.reply_to(message, "Ovozli xabar qabul qilindi. Hisobot tayyorlanmoqda...")
            report, excel_file = process_agent_request("Ovozli topshiriq bo'yicha: Iltimos, batafsil hisobot tayyorlab ber va kerak bo'lsa Excel jadvalini yarat.")
            bot.send_message(message.chat.id, report)
            if excel_file:
                fpath = os.path.join(BASE_DIR, excel_file)
                if os.path.exists(fpath):
                    with open(fpath, "rb") as doc:
                        bot.send_document(message.chat.id, doc, caption="📥 Siz so'ragan tayyor Excel hisoboti")
        except Exception as e:
            bot.reply_to(message, f"Xatolik yuz berdi: {e}")

    print("Telegram bot ishga tushdi...")
    bot.infinity_polling()

if __name__ == "__main__":
    t = threading.Thread(target=run_web_server, daemon=True)
    t.start()
    run_telegram_bot()
