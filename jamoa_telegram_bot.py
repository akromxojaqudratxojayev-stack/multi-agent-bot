import os
import threading
try:
    import telebot
    from flask import Flask
    from google import genai
    from google.genai import types
except ImportError:
    print("Xatolik: Kutubxonalar yo'q. Terminalda yozing: pip install google-genai pyTelegramBotAPI flask")
    exit(1)

# XAVFSIZLIK: Kalitlarni ochiq yozmaymiz, serverning o'zidan (Environment) o'qiymiz!
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "SIZNING_TELEGRAM_TOKENINGIZ")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "SIZNING_GEMINI_KALITINGIZ")

# =======================================================
# UPTIMEROBOT UCHUN WEB-SERVER (Bot uxlamasligi uchun)
# =======================================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Jamoa AI Boti faol ishlamoqda!"

def run_web_server():
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)

# =======================================================
# MULTI-AGENT BOT KODI
# =======================================================
def main():
    if TELEGRAM_BOT_TOKEN == "SIZNING_TELEGRAM_TOKENINGIZ" or GEMINI_API_KEY == "SIZNING_GEMINI_KALITINGIZ":
        print("DIQQAT: Environment variables (API kalitlar) kiritilmagan!")
        
    bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    google_search_tool = {"google_search": {}}
    
    creative_agent = client.chats.create(
        model="gemini-1.5-flash",
        config=types.GenerateContentConfig(
            tools=[google_search_tool],
            system_instruction="Sen Kreativ Agentsan. Vazifang: Video roliklar ssenariysi, rasm dizaynlari tayyorlash. Internetdan (Google) so'nggi zamonaviy trendlarni izlab top.",
            temperature=0.7,
        )
    )
    
    finance_agent = client.chats.create(
        model="gemini-1.5-flash",
        config=types.GenerateContentConfig(
            tools=[google_search_tool],
            system_instruction="Sen Moliya va Iqtisodiyot Agentisan. Vazifang: aniq hisob-kitoblar, byudjet, biznes reja. Internetdan tovarlarning narxlari va eng arzon variantlarini qidir.",
            temperature=0.1,
        )
    )
    
    tech_agent = client.chats.create(
        model="gemini-1.5-flash",
        config=types.GenerateContentConfig(
            tools=[google_search_tool],
            system_instruction="Sen Arxitektura va Dasturlash Agentisan. Vazifang: Saytlar yaratish, IT infratuzilma. Internetdan raqobatchilarning saytlarini o'rgan.",
            temperature=0.2,
        )
    )

    def kreativ_bolimga_topshiriq(topshiriq: str) -> str:
        return creative_agent.send_message(topshiriq).text

    def moliya_bolimiga_topshiriq(topshiriq: str) -> str:
        return finance_agent.send_message(topshiriq).text

    def dasturchi_bolimga_topshiriq(topshiriq: str) -> str:
        return tech_agent.send_message(topshiriq).text

    director_tools = [kreativ_bolimga_topshiriq, moliya_bolimiga_topshiriq, dasturchi_bolimga_topshiriq]
    user_directors = {}

    def get_director(user_id):
        if user_id not in user_directors:
            user_directors[user_id] = client.chats.create(
                model="gemini-1.5-flash", 
                config=types.GenerateContentConfig(
                    tools=director_tools,
                    temperature=0.3,
                    system_instruction=(
                        "Sen ushbu tizimning Bosh Direktori (Manager)san. Qo'l ostingda 3 ta xodim bor: Kreativ, Moliya va Dasturchi. Ular internetga ulangan! "
                        "Foydalanuvchi senga topshiriq beradi. Sen vazifani xodimlarga bo'lib berasan. Ularning ishini O'ZING TEKSHIRASAN. "
                        "Faqatgina mukammal variantni yig'ib foydalanuvchiga taqdim etasan."
                    )
                )
            )
        return user_directors[user_id]
        
    @bot.message_handler(commands=['start'])
    def send_welcome(message):
        bot.reply_to(message, "Hurmatli rahbar! Men sizning Bosh Direktoringizman. Menga xohlagan ishingizni yozma yoki ovozli qilib yuboring.")

    @bot.message_handler(content_types=['text'])
    def handle_text(message):
        bot.send_chat_action(message.chat.id, 'typing')
        try:
            director = get_director(message.chat.id)
            response = director.send_message(message.text)
            bot.send_message(message.chat.id, f"✅ **DIREKTOR XISOBOTI:**\n\n{response.text}", parse_mode='Markdown')
        except Exception as e:
            bot.reply_to(message, f"Xatolik yuz berdi: {e}")

    @bot.message_handler(content_types=['voice'])
    def handle_voice(message):
        bot.send_chat_action(message.chat.id, 'typing')
        try:
            file_info = bot.get_file(message.voice.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            audio_part = types.Part.from_bytes(data=downloaded_file, mime_type='audio/ogg')
            
            director = get_director(message.chat.id)
            response = director.send_message(["Ushbu ovozli topshiriqni eshiting va xodimlaringiz orqali mukammal qilib bajaring:", audio_part])
            bot.send_message(message.chat.id, f"✅ **DIREKTOR XISOBOTI:**\n\n{response.text}", parse_mode='Markdown')
        except Exception as e:
            bot.reply_to(message, f"Xatolik yuz berdi: {e}")
            
    # Telegram botni ishga tushirish
    print("Telegram bot ishga tushdi...")
    bot.infinity_polling()

if __name__ == "__main__":
    # Web-serverni orqa fonda alohida ishga tushiramiz (UptimeRobot uchun)
    t = threading.Thread(target=run_web_server)
    t.start()
    
    # Asosiy botni ishga tushiramiz
    main()
