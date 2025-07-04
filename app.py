# app.py (FINAL - Render Login Helper Version)
import os
import asyncio
import threading
import json
import logging
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import SessionPasswordNeeded

# --- Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s')
logger_control = logging.getLogger('ControlBot')
logger_user = logging.getLogger('UserBot')

flask_app = Flask(__name__)
@flask_app.route('/')
def health_check(): return "Bot is alive!", 200
def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

# --- Environment Variable Loading ---
def get_env(name, message, required=True, cast=str):
    val = os.environ.get(name)
    if val: return cast(val)
    if required: logging.critical(message); exit(1)
    return None

API_ID = get_env('API_ID', 'API_ID not set!', cast=int)
API_HASH = get_env('API_HASH', 'API_HASH not set!')
BOT_TOKEN = get_env('BOT_TOKEN', 'BOT_TOKEN not set!')
ADMIN_ID = get_env('ADMIN_ID', 'ADMIN_ID not set!', cast=int)
# SESSION_STRING is now optional. We will generate it.
SESSION_STRING = get_env('SESSION_STRING', 'SESSION_STRING not set.', required=False)

# --- Pyrogram Clients ---
control_bot = Client("control_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
admin_filter = filters.user(ADMIN_ID)
login_process_active = False

# --- Control Bot Commands ---
@control_bot.on_message(filters.command("start") & admin_filter)
async def start_command(client, message):
    if SESSION_STRING:
        await message.reply_text("✅ Bot is online and the user account is logged in. Forwarding is active.")
    else:
        await message.reply_text("👋 Bot is online. The user account is NOT logged in.\n\nPlease use the `/login` command to generate your session string.")

@control_bot.on_message(filters.command("login") & admin_filter)
async def login_command(client, message):
    global login_process_active
    if login_process_active:
        await message.reply_text("A login process is already active.")
        return
    
    login_process_active = True
    temp_client = Client(":memory:", api_id=API_ID, api_hash=API_HASH)
    
    try:
        await temp_client.connect()
        phone_number = await client.ask(ADMIN_ID, "Please send your phone number in international format (e.g., +91...):", filters=filters.text, timeout=300)
        
        sent_code = await temp_client.send_code(phone_number.text)
        
        otp = await client.ask(ADMIN_ID, "An OTP has been sent to your Telegram account. Please send it here:", filters=filters.text, timeout=300)

        await temp_client.sign_in(phone_number.text, sent_code.phone_code_hash, otp.text)
        
    except SessionPasswordNeeded:
        password = await client.ask(ADMIN_ID, "Your account has 2FA enabled. Please send your password:", filters=filters.text, timeout=300)
        await temp_client.check_password(password.text)
        
    except Exception as e:
        await message.reply_text(f"❌ Login failed. Error: {e}")
        login_process_active = False
        await temp_client.disconnect()
        return

    session_str = await temp_client.export_session_string()
    await temp_client.disconnect()
    
    await message.reply_text(
        "✅ **Login Successful!**\n\n"
        "Here is your session string. It is a secret!\n\n"
        "1. Copy this string.\n"
        "2. Go to your Render dashboard -> Environment.\n"
        "3. Create a new environment variable named `SESSION_STRING`.\n"
        "4. Paste this string as the value and mark it as a secret.\n"
        "5. The bot will restart automatically, and the forwarder will be active.\n\n"
        f"<code>{session_str}</code>"
    )
    login_process_active = False

# --- Userbot and Main Startup ---
async def run_userbot_if_configured():
    if not SESSION_STRING:
        logger_user.info("SESSION_STRING not set. Userbot will not be started.")
        return

    logger_user.info("SESSION_STRING found. Starting Userbot...")
    user_bot = Client("user_bot_session", session_string=SESSION_STRING, in_memory=True)
    
    # You can add your forwarding logic here later.
    # For now, we just want to see it log in.
    @user_bot.on_message(filters.all)
    async def log_all(client, message):
        logger_user.info(f"Userbot saw a message in chat: {message.chat.id}")

    try:
        await user_bot.start()
        me = await user_bot.get_me()
        logger_user.info(f"UserBot started successfully as {me.first_name}")
        await control_bot.send_message(ADMIN_ID, f"✅ **Forwarder is ACTIVE!**\nUser account logged in: **{me.first_name}**")
    except Exception as e:
        logger_user.error(f"CRITICAL: Userbot failed to start. Is SESSION_STRING valid? Error: {e}")
        await control_bot.send_message(ADMIN_ID, f"❌ **ERROR:** Userbot failed to start.\nReason: `{e}`")

async def main():
    # Start the control bot first, always.
    await control_bot.start()
    me_control = await control_bot.get_me()
    logger_control.info(f"Control Bot started as {me_control.first_name}")

    # Then, start the userbot in a background task so it doesn't block anything.
    asyncio.create_task(run_userbot_if_configured())
    
    await asyncio.Event().wait()

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger_control.info("Starting application...")
    asyncio.run(main())