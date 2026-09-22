import os
import asyncio
import logging
import sqlite3
import threading
from flask import Flask
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ChatMemberUpdated, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.enums import ChatMemberStatus

# --- ENV VARIABLES ---
API_TOKEN = os.getenv("API_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "")
PORT = int(os.getenv("PORT", 10000))
# አማራጭ: የኦነር ቴሌግራም ID ካለዎት እዚህ ያስገቡ (አልያም bot ላይ /myid ብለው ማወቅ ይቻላል)
OWNER_ID = int(os.getenv("OWNER_ID", "0"))  # ማስገባት ካልፈለጉ 0 ይტዉትና ሪፖርት በ /admin ሲጠየቅ ማሳየት እንችላለን

if not API_TOKEN or CHANNEL_ID == 0:
    raise ValueError("❌ API_TOKEN ወይም CHANNEL_ID አልተሰጠም! Render Environment Variables ይመልከቱ።")

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- DATABASE SETUP (SQLite) ---
DB_NAME = 'referral_bot.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            invite_link TEXT,
            invite_count INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS invite_links (
            invite_link TEXT PRIMARY KEY,
            user_id INTEGER
        )
    ''')
    conn.commit()
    conn.close()

# --- KEYBOARD ---
def get_main_keyboard():
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 የጋበዝኩት ሰው ብዛት")]
        ],
        resize_keyboard=True
    )
    return kb

# --- FLASK APP (ისთვის Port እንዲኖር) ---
app = Flask(__name__)

@app.route('/')
def index():
    return "🤖 Telegram Referral Bot is running and healthy!"

def run_flask():
    app.run(host='0.0.0.0', port=PORT)

# --- AIOGRAM HANDLERS ---
@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or "None"
    full_name = message.from_user.full_name or "ተጠቃሚ"
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("SELECT invite_link, invite_count FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if row:
        my_link, count = row
    else:
        try:
            invite_obj = await bot.create_chat_invite_link(
                chat_id=CHANNEL_ID,
                name=f"ref_{user_id}",
                creates_join_request=False
            )
            my_link = invite_obj.invite_link
            count = 0
            cursor.execute(
                "INSERT INTO users (user_id, username, full_name, invite_link, invite_count) VALUES (?, ?, ?, ?, ?)",
                (user_id, username, full_name, my_link, 0)
            )
            cursor.execute("INSERT OR REPLACE INTO invite_links (invite_link, user_id) VALUES (?, ?)", (my_link, user_id))
            conn.commit()
        except Exception as e:
            conn.close()
            await message.answer(f"❌ ሊንክ መፍጠር አልተቻለም። Admin መሆኑን ያረጋግጡ።\nስህተት: {e}")
            return

    conn.close()
    
    text = (
        f"👋 ሰላም <b>{full_name}</b>!\n\n"
        f"🔗 <b>የእርስዎ ልዩ መጋበዣ LINK:</b>\n<code>{my_link}</code>\n\n"
        f"👥 የጋበዟቸው ሰው ብዛት: <b>{count}</b> ሰው\n\n"
        f"💡 በዚህ የእርሶ ብቻ ልዩ referal link 15 የ 2019 remedial ተማሪዎችን ሲጋብዙ የ remedial matrix Bot እና remedial matrix tutorial 2019 ክፍት ይደረግልዎታል ምንም ሳይከፍል🎓"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_keyboard())

@dp.message(F.text == "📊 የጋበዝኩት ሰው ብዛት")
@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    user_id = message.from_user.id
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT invite_count, invite_link FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        count, my_link = row
    else:
        count, my_link = 0, "የለዎትም"

    if count >= 15:
        await message.answer(
            f"🎉እንኳን ደስ አለዎት! 15 የ2019 remedial ተማሪዎችን ጋብዘዋል!\n"
            f"👥 አጠቃላይ ግብዣዎ: <b>{count}</b> ሰው\n\n"
            f"🔓 ቱቶሪያል እና ቦቱ እንዲከፈትልዎ እባክዎ ውድ <b>@remedial_matrix_support</b> ያናግሩኝ!",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )
    else:
        remaining = 15 - count
        await message.answer(
            f"📊 እስካሁን የጋበዟቸው ሰው ብዛት: <b>{count}</b> ሰው\n"
            f"🎯 ከ 15 ለመድረስ የቀረዎት: <b>{remaining}</b> ሰው\n\n"
            f"🔗 የእርስዎ ሊንክ:\n<code>{my_link}</code>\n\n"
            f"💡 15 ሲሞሉ <b>@remedial_matrix_support</b> ያናግሩኝ!",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )

# --- OWNER ADMIN REPORT COMMAND ---
@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    user_id = message.from_user.id
    # አማራጭ: ማንኛውም ሰው እንዳያይ ማድረግ ከፈለጉ (OWNER_ID != 0 and user_id != OWNER_ID) ማጥራት ይቻላል። 
    # ግን ለአሁኑ ትዕዛዙን የላከው ማንም ይሁን ወይም ራሱ owner ሲል ሙሉ ሪፖርት እንስጥ:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, full_name, username, invite_link, invite_count FROM users")
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        await message.answer("📁 እስካሁን የተመዘገበ ተጠቃሚ የለም።")
        return
    
    report_text = "📋 <b>የሁሉም ተጠቃሚዎች ሪፖርት (Owner Report):</b>\n\n"
    for r in rows:
        uid, fname, uname, ulink, ucount = r
        report_text += (
            f"👤 ስም: <b>{fname}</b> (ID: <code>{uid}</code>, @{uname})\n"
            f"🔗 ሊንክ: <code>{ulink}</code>\n"
            f"👥 ጋበዘው: <b>{ucount}</b> ሰው\n"
            f"----------------------------------\n"
        )
        # ሜሴጅ በጣም እንዳይረዝም (Telegram limit 4096chars)
        if len(report_text) > 3500:
            await message.answer(report_text, parse_mode="HTML")
            report_text = ""
            
    if report_text:
        await message.answer(report_text, parse_mode="HTML")

@dp.chat_member()
async def track_chat_member(event: ChatMemberUpdated):
    if event.chat.id != CHANNEL_ID:
        return
    
    old_status = event.old_chat_member.status
    new_status = event.new_chat_member.status
    
    if old_status in [ChatMemberStatus.LEFT, ChatMemberStatus.BANNED] and new_status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR]:
        invite_link_obj = event.invite_link
        if invite_link_obj and invite_link_obj.invite_link:
            used_link = invite_link_obj.invite_link
            
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM invite_links WHERE invite_link = ?", (used_link,))
            row = cursor.fetchone()
            
            if row:
                referrer_id = row[0]
                new_user_id = event.new_chat_member.user.id
                
                if referrer_id != new_user_id:
                    cursor.execute("UPDATE users SET invite_count = invite_count + 1 WHERE user_id = ?", (referrer_id,))
                    conn.commit()
                    
                    try:
                        cursor.execute("SELECT invite_count FROM users WHERE user_id = ?", (referrer_id,))
                        updated_count = cursor.fetchone()[0]
                        if updated_count >= 15:
                            await bot.send_message(
                                referrer_id,
                                f"🎉 <b>እንኳን ደስ አለዎት!</b> 15 ሰዎችን ሞልተዋል!\n"
                                f"👥 አጠቃላይ ግብዣዎ: <b>{updated_count}</b> ሰው\n"
                                f"🔓 ቱቶሪያል እንዲከፈትልዎ እባክዎ <b>@remedial_matrix_support</b> ያናግሩኝ!",
                                parse_mode="HTML"
                            )
                        else:
                            await bot.send_message(
                                referrer_id,
                                f"🎉 <b>እንኳን ደስ አለዎት!</b> አዲስ ሰው በሊንክዎ ቻናሉን ገብቷል.\n"
                                f"👥 አጠቃላይ ግብዣዎ: <b>{updated_count}</b> ሰው (ከ15 ለመድረስ {15 - updated_count} ቀርቷል)",
                                parse_mode="HTML"
                            )
                    except Exception:
                        pass
            conn.close()

async def main():
    init_db()
    logging.basicConfig(level=logging.INFO)
    print("🤖 ቦቱ እና ፍላስክ ሰርቨር መሥራት ጀምረዋል...")
    
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
