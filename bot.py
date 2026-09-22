import os
import asyncio
import logging
import sqlite3
import threading
from flask import Flask
from aiogram import Bot, Dispatcher
from aiogram.types import Message, ChatMemberUpdated
from aiogram.filters import CommandStart, Command
from aiogram.enums import ChatMemberStatus

# --- ENV VARIABLES ---
API_TOKEN = os.getenv("API_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "")
PORT = int(os.getenv("PORT", 10000))

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
            cursor.execute("INSERT INTO users (user_id, invite_link, invite_count) VALUES (?, ?, ?)", (user_id, my_link, 0))
            cursor.execute("INSERT OR REPLACE INTO invite_links (invite_link, user_id) VALUES (?, ?)", (my_link, user_id))
            conn.commit()
        except Exception as e:
            conn.close()
            await message.answer(f"❌ ሊንክ መፍጠር አልተቻለም። Admin መሆኑን ያረጋግጡ።\nስህተት: {e}")
            return

    conn.close()
    
    first_name = message.from_user.first_name or "ተጠቃሚ"
    text = (
        f"👋 ሰላም <b>{first_name}</b>!\n\n"
        f"🔗 <b>የእርስዎ ልዩ የኢንቫይት ሊንክ:</b>\n<code>{my_link}</code>\n\n"
        f"📢 <b>ቻናላችን:</b> https://t.me/{CHANNEL_USERNAME}\n"
        f"👥 የጋበዟቸው ሰው ብዛት: <b>{count}</b> ሰው\n\n"
        f"💡 ይህንን ሊንክ በመላክ ሰዎችን ወደ ቻናሉ ይጋብዙ!"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    user_id = message.from_user.id
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT invite_count FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    count = row[0] if row else 0
    await message.answer(f"📊 አጠቃላይ የጋበዟቸው ሰው ብዛት: <b>{count}</b> ሰው", parse_mode="HTML")

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
                        await bot.send_message(
                            referrer_id,
                            f"🎉 <b>እንኳን ደስ አለዎት!</b> አዲስ ሰው በሊንክዎ ቻናሉን ገብቷል.\n"
                            f"👥 አጠቃላይ ግብዣዎ: <b>{updated_count}</b> ሰው",
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass
            conn.close()

async def main():
    init_db()
    logging.basicConfig(level=logging.INFO)
    print("🤖 ቦቱ እና ፍላስክ ሰርቨር መሥራት ጀምረዋል...")
    
    # Flask ን በ Thread ማስጀመር
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # Aiogram Polling ማስጀመር
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
