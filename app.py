# app.py (Simple, Stateless, and Final)
import os
import asyncio
import threading
import json
import logging
import requests
from flask import Flask
from pyrogram import Client, filters, errors
from pyrogram.types import Message

# --- Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s')
logger_control = logging.getLogger('ControlBot')
logger_user = logging.getLogger('UserBot')

flask_app = Flask(__name__)
@flask_app.route('/')
def health_check(): return "Bot is alive!", 200
def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)

# --- Environment Variable Loading ---
def get_env(name, message, cast=str, required=True):
    val = os.environ.get(name)
    if val:
        return cast(val)
    if required:
        logging.critical(message)
        exit(1)
    return None

API_ID = get_env('API_ID', 'API_ID not set.', int)
API_HASH = get_env('API_HASH', 'API_HASH not set.')
BOT_TOKEN = get_env('BOT_TOKEN', 'BOT_TOKEN not set.')
ADMIN_ID = get_env('ADMIN_ID', 'ADMIN_ID not set.', int)
CONFIG_CHANNEL_ID = get_env('CONFIG_CHANNEL_ID', 'CONFIG_CHANNEL_ID not set.', int)
USER_SESSION_STRING = get_env('USER_SESSION_STRING', 'USER_SESSION_STRING not set.', required=False)

config_message_id = None

# --- Configuration Management via Telegram Channel ---
async def get_config_message_id_and_data(client):
    global config_message_id
    if config_message_id:
        try:
            msg = await client.get_messages(CONFIG_CHANNEL_ID, config_message_id)
            return config_message_id, json.loads(msg.text)
        except Exception:
            config_message_id = None # Reset if message is not found

    try:
        async for msg in client.get_chat_history(CONFIG_CHANNEL_ID, limit=50):
             if msg.is_pinned and msg.text.startswith('{'):
                 config_message_id = msg.id
                 logger_control.info(f"Found pinned config message with ID: {config_message_id}")
                 return config_message_id, json.loads(msg.text)
    except Exception as e:
        logger_control.error(f"Could not search for config message. Is bot an admin in the channel? Error: {e}")
    
    logger_control.warning("No valid pinned config message found. Use /bootstrap.")
    return None, {}

async def save_config(client, config_data):
    msg_id, _ = await get_config_message_id_and_data(client)
    if not msg_id:
        logger_control.error("Cannot save config, no config message ID. Use /bootstrap.")
        return
    try:
        await client.edit_message_text(CONFIG_CHANNEL_ID, msg_id, json.dumps(config_data, indent=4))
    except Exception as e:
        logger_control.error(f"Failed to save config: {e}")

# --- Pyrogram Clients Setup (Using in_memory to avoid file errors) ---
control_bot = Client("control_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
user_bot = None
admin_filter = filters.user(ADMIN_ID)

# --- Control Bot Command Handlers ---
@control_bot.on_message(filters.command("start") & admin_filter)
async def start_command(client, message: Message):
    await message.reply_text("👋 Welcome! Bot is online.\n\nUse `/bootstrap` to initialize storage if this is your first time.")

@control_bot.on_message(filters.command("bootstrap") & admin_filter)
async def bootstrap(client, message: Message):
    try:
        msg = await client.send_message(CONFIG_CHANNEL_ID, text=json.dumps({}, indent=4))
        await client.pin_chat_message(CONFIG_CHANNEL_ID, msg.id, disable_notification=True)
        global config_message_id
        config_message_id = msg.id
        await message.reply_text(f"✅ Successfully bootstrapped config storage in your channel.")
    except Exception as e:
        await message.reply_text(f"❌ Failed to bootstrap. Ensure the bot is an admin in the config channel with pin permissions. Error: {e}")

@control_bot.on_message(filters.command("getsession") & admin_filter)
async def get_session_command(client, message: Message):
    await message.reply_text("Please send the phone number for the forwarding account (e.g., +11234567890).")
    try:
        phone_msg = await client.listen(chat_id=message.chat.id, user_id=ADMIN_ID, timeout=300)
        phone = phone_msg.text
        
        temp_client = Client(":memory:", api_id=API_ID, api_hash=API_HASH)
        await temp_client.connect()
        sent_code = await temp_client.send_code(phone)
        await phone_msg.reply("OTP sent. Please send it here.")
        
        otp_msg = await client.listen(chat_id=message.chat.id, user_id=ADMIN_ID, timeout=300)
        otp = otp_msg.text
        
        await temp_client.sign_in(phone, sent_code.phone_code_hash, otp)
    except errors.SessionPasswordNeeded:
        await otp_msg.reply("2FA password needed. Please send it here.")
        pass_msg = await client.listen(chat_id=message.chat.id, user_id=ADMIN_ID, timeout=300)
        password = pass_msg.text
        await temp_client.check_password(password)
    except Exception as e:
        await message.reply_text(f"An error occurred: {e}")
        if 'temp_client' in locals() and temp_client.is_connected:
            await temp_client.disconnect()
        return

    session_string = await temp_client.export_session_string()
    await temp_client.disconnect()
    await message.reply_text(f"✅ **Session String Generated**\n\nAdd this to your Koyeb Environment Variables as `USER_SESSION_STRING`:\n\n<code>{session_string}</code>")

# (Add your /add, /addsource, /delete, /list handlers here, they are unchanged)
# ...

# --- Main Application Start ---
async def main():
    global user_bot
    await control_bot.start()
    logger_control.info("Control Bot started.")

    if USER_SESSION_STRING:
        logger_user.info("USER_SESSION_STRING found, starting UserBot.")
        user_bot = Client("user_bot_session", session_string=USER_SESSION_STRING, in_memory=True)
        
        @user_bot.on_message(group=1)
        async def forwarder_handler(client, message):
            _, config = await get_config_message_id_and_data(control_bot)
            forwards = config.get("forwards", {})
            for name, rule in forwards.items():
                if message.chat.id in rule.get("sources", []):
                    dest = rule.get("destination")
                    logger_user.info(f"Forwarding from {message.chat.id} to {dest}")
                    try: await message.copy(dest)
                    except Exception as e: logger_user.error(f"Forward failed: {e}")
                    break
        try:
            await user_bot.start()
            logger_user.info(f"UserBot started as {(await user_bot.get_me()).first_name}")
        except Exception as e:
            logger_user.error(f"UserBot failed to start with session string: {e}")

    await asyncio.Event().wait()


if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger_control.info("Starting application...")
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Application stopped.")