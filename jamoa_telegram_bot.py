import os
import threading
import glob
try:
    import telebot
    from flask import Flask
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from google import genai
    from google.genai import types
except ImportError:
    print("Xatolik: Kutubxonalar yo'q. Terminalda yozing: pip install google-genai pyTelegramBotAPI flask openpyxl")
    exit(1)

# XAVFSIZLIK: Kalitlarni FAQAT serverdan (Environment) olamiz, hech qachon ochiq yozmaymiz!
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
OWNER_ID = os.environ.get("OWNER_ID", "") # Sizning shaxsiy Telegram ID raqamingiz

# =======================================================
# UPTIMEROBOT UCHUN WEB-SERVER
# =======================================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Jamoa AI Boti faol ishlamoqda!"

def run_web_server():
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)

# =======================================================
# HAQIQIY EXCEL (.XLSX) YARATISH ASBOBI
# =======================================================
def excel_fayl_yaratish(fayl_nomi: str, ustunlar: list[str], qatorlar: list[list[str]]) -> str:
    """
    Haqiqiy professional Excel (.xlsx) fayl yaratadi. 
    Har bir ma'lumot alohida katakda (A, B, C, D...), chiroyli rang va chegaralar bilan bo'ladi.
    """
    if not fayl_nomi.endswith('.xlsx'):
        fayl_nomi = fayl_nomi.replace('.csv', '') + '.xlsx'
        
    print(f"📊 [Excel Asbob]: {fayl_nomi} yaratilmoqda...")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Hisobot"
    
    # Chiroyli sarlavha dizayni (Ko'k rang, oq qalin yozuv)
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    data_font = Font(name="Calibri", size=11)
    
    thin_border = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )
    
    # 1. Ustunlarni yozish
    ws.append(ustunlar)
    for col_num in range(1, len(ustunlar) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border
        
    # 2. Qatorlarni yozish
    for row_idx, row_data in enumerate(qatorlar, start=2):
        ws.append(row_data)
        for col_num in range(1, len(row_data) + 1):
            cell = ws.cell(row=row_idx, column=col_num)
            cell.font = data_font
            cell.border = thin_border
            # Raqamlar bo'lsa o'rtaga yoki o'ngga
            if str(cell.value).replace(' ', '').replace(',', '').replace('.', '').isdigit():
                cell.alignment = Alignment(horizontal="right", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")
                
    # 3. Ustun kengliklarini avtomatik to'g'irlash (hech narsa qisilib qolmasligi uchun)
    for col in ws.columns:
        max_length = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        ws.column_dimensions[col_letter].width = max(max_length + 4, 12)
        
    ws.row_dimensions[1].height = 26
    wb.save(fayl_nomi)
    return fayl_nomi

# =======================================================
# MULTI-AGENT BOT KODI
# =======================================================
def main():
    bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    google_search_tool = {"google_search": {}}
    
    # 1. XODIMLAR
    creative_agent = client.chats.create(
        model="gemini-3.8-flash",
        config=types.GenerateContentConfig(
            tools=[google_search_tool],
            system_instruction="Sen Kreativ Agentsan. Video, rasm va dizayn g'oyalarini donama-dona, tartibli punktlar bilan tayyorla.",
            temperature=0.7,
        )
    )
    
    finance_agent = client.chats.create(
        model="gemini-3.8-flash",
        config=types.GenerateContentConfig(
            tools=[google_search_tool],
            system_instruction="Sen Moliya va Bozor tahlilchisisan. Internetdan aniq narxlarni, jadval ma'lumotlarini izlab top va aniq raqamlarda hisoblab ber.",
            temperature=0.1,
        )
    )
    
    tech_agent = client.chats.create(
        model="gemini-3.8-flash",
        config=types.GenerateContentConfig(
            tools=[google_search_tool],
            system_instruction="Sen IT va Arxitektura mutaxassisisan. Tizim rejasini aniq bandlar bilan yoz.",
            temperature=0.2,
        )
    )

    def kreativ_bolimga_topshiriq(topshiriq: str) -> str:
        return creative_agent.send_message(topshiriq).text

    def moliya_bolimiga_topshiriq(topshiriq: str) -> str:
        return finance_agent.send_message(topshiriq).text

    def dasturchi_bolimga_topshiriq(topshiriq: str) -> str:
        return tech_agent.send_message(topshiriq).text

    director_tools = [
        kreativ_bolimga_topshiriq, 
        moliya_bolimiga_topshiriq, 
        dasturchi_bolimga_topshiriq,
        excel_fayl_yaratish
    ]
    user_directors = {}

    def get_director(user_id):
        if user_id not in user_directors:
            user_directors[user_id] = client.chats.create(
                model="gemini-3.8-flash", 
                config=types.GenerateContentConfig(
                    tools=director_tools,
                    temperature=0.3,
                    system_instruction=(
                        "Sen professional Bosh Direktorsan. Sening qo'lingda Kreativ, Moliya, Dasturchi xodimlar va 'excel_fayl_yaratish' asbobi bor.\n"
                        "JAVOBINGNI FORMATLASH BO'YICHA ENG MUHIM TALABLAR:\n"
                        "1. Ma'lumotlarni hech qachon matn ichida aralashtirib yuborma! Xuddi rasmiy tender yoki hisobotdek DONAMA-DONA, har bir ma'lumotni alohida qatorda ko'rsat.\n"
                        "2. Emojilardan aniq va chiroyli foydalan (masalan: 📌 Lot/Mavzu, 🏛️ Tashkilot/Manba, 💰 Narx/Summa, 📦 Hajm/Vazn, 🚚 Muddat, 📅 Sana, 📝 Izoh, 🔹 Bandlar).\n"
                        "3. Agar foydalanuvchi hisobot, narxlar ro'yxati, reja yoki jadval so'rasa yoki Excel haqida gapirsa, ALBATTA 'excel_fayl_yaratish' asbobini chaqirib, fayl yarat!\n"
                        "4. Foydalanuvchiga matnli hisobot berish bilan birga, 'Siz uchun to'liq Excel fayl tayyorlandi va pastda yuklandi' deb ayt."
                    )
                )
            )
        return user_directors[user_id]

    def send_created_files(chat_id):
        """Yaratilgan barcha .xlsx fayllarni Telegramga yuklab, so'ng o'chiradi."""
        files = glob.glob("*.xlsx")
        for fpath in files:
            try:
                with open(fpath, "rb") as doc:
                    bot.send_document(chat_id, doc, caption="📥 Siz so'ragan tayyor Excel hisoboti")
                os.remove(fpath)
            except Exception as e:
                print(f"Fayl yuborishda xatolik: {e}")

    def check_access(message):
        if OWNER_ID and str(message.chat.id) != str(OWNER_ID):
            bot.reply_to(message, "⛔ Kechirasiz! Bu shaxsiy AI Agent boti. Undan faqat uning haqiqiy egasi foydalana oladi.")
            return False
        return True

    @bot.message_handler(commands=['start', 'myid'])
    def send_welcome(message):
        if not check_access(message):
            return
        bot.reply_to(message, f"Salom hurmatli rahbar! Men sizning shaxsiy Bosh Direktoringizman.\n\n🆔 Sizning Telegram ID: `{message.chat.id}`\n\nMenga xohlagan topshiriqni bering, barcha ma'lumotlarni donama-dona qilib tahlil qilib, kerak bo'lsa tayyor Excel (.xlsx) faylini ham yuklab beraman! 📊", parse_mode='Markdown')

    @bot.message_handler(content_types=['text'])
    def handle_text(message):
        if not check_access(message):
            return
        bot.send_chat_action(message.chat.id, 'typing')
        try:
            director = get_director(message.chat.id)
            response = director.send_message(message.text)
            bot.send_message(message.chat.id, response.text)
            # Agar Excel yaratilgan bo'lsa, faylni yuboramiz
            send_created_files(message.chat.id)
        except Exception as e:
            bot.reply_to(message, f"Xatolik yuz berdi: {e}")

    @bot.message_handler(content_types=['voice'])
    def handle_voice(message):
        if not check_access(message):
            return
        bot.send_chat_action(message.chat.id, 'typing')
        try:
            file_info = bot.get_file(message.voice.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            audio_part = types.Part.from_bytes(data=downloaded_file, mime_type='audio/ogg')
            
            director = get_director(message.chat.id)
            response = director.send_message(["Ushbu ovozli topshiriqni bajaring, tushunarli qilib donama-dona formatda xisobot bering va kerak bo'lsa Excel fayl qilib tayyorlang:", audio_part])
            bot.send_message(message.chat.id, response.text)
            # Agar Excel yaratilgan bo'lsa, faylni yuboramiz
            send_created_files(message.chat.id)
        except Exception as e:
            bot.reply_to(message, f"Xatolik yuz berdi: {e}")

    print("Telegram bot ishga tushdi...")
    bot.infinity_polling()

if __name__ == "__main__":
    t = threading.Thread(target=run_web_server)
    t.start()
    main()
