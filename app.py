# app.py (Bare Minimum Test Version)
import os
import threading
import logging
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import Message

# --- Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s')
logger_bot = logging.getLogger('TestBot')

flask_app = Flask(__name__)
@flask_app.route('/')
def health_check(): return "Bare Minimum Bot is alive!", 200
def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)

# --- Environment Variable Loading ---
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    logger_bot.critical("FATAL: BOT_TOKEN environment variable is not set!")
    exit()

# --- Pyrogram Client ---
# We use hardcoded API_ID and API_HASH because they are public values from Telegram's own examples.
# This removes them as a potential source of error.
# We also run in_memory=True to avoid any file system errors.
app = Client("my_test_bot", api_id=6, api_hash="eb06d4abfb49dc3eeb1aeb98ae0f581e", bot_token=BOT_TOKEN, in_memory=True)

# --- The ONLY Command Handler ---
# There is NO admin filter. Anyone can use this command.
@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    user_id = message.from_user.id
    logger_bot.info(f"Received /start command from user ID: {user_id}")
    await message.reply_text(f"✅ Hello! I am online.\nYour User ID is: <code>{user_id}</code>")

# --- Main Application Start ---
if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger_bot.info("Starting Bare Minimum Test Bot...")
    app.run()