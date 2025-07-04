# app.py (FINAL - "Telegram as Database" Version)
import os
import asyncio
import threading
import json
import logging
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
def get_env(name, message, required=True, cast=str):
    val = os.environ.get(name)
    if val: return cast(val)
    if required: logging.critical(message); exit(1)
    return None

API_ID = get_env('API_ID', 'API_ID not set!', cast=int)
API_HASH = get_env('API_HASH', 'API_HASH not set!')
BOT_TOKEN = get_env('BOT_TOKEN', 'BOT_TOKEN not set!')
ADMIN_ID = get_env('ADMIN_ID', 'ADMIN_ID not set!', cast=int)
CONFIG_CHANNEL_ID = get_env('CONFIG_CHANNEL_ID', 'CONFIG_CHANNEL_ID not set!', cast=int)
USER_SESSION_STRING = get_env('USER_SESSION_STRING', 'USER_SESSION_STRING not set!', required=False)

config_message_id = None

# --- Configuration Management via Telegram Channel ---
async def get_config_message_id_and_data(client):
    global config_message_id
    if config_message_id:
        try:
            msg = await client.get_messages(CONFIG_CHANNEL_ID, config_message_id)
            return config_message_id, json.loads(msg.text)
        except Exception:
            config_message_id = None
    try:
        async for msg in client.get_chat_history(CONFIG_CHANNEL_ID, limit=50):
             if msg.is_pinned and msg.text.startswith('{'):
                 config_message_id = msg.id
                 return config_message_id, json.loads(msg.text)
    except Exception as e:
        logger_control.error(f"Could not search for config message: {e}")
    return None, {}

async def save_config(client, config_data):
    msg_id, _ = await get_config_message_id_and_data(client)
    if not msg_id:
        logger_control.error("Cannot save config, no config message ID. Use /bootstrap."); return
    try:
        await client.edit_message_text(CONFIG_CHANNEL_ID, msg_id, json.dumps(config_data, indent=4))
    except Exception as e:
        logger_control.error(f"Failed to save config: {e}")

# --- Pyrogram Clients ---
control_bot = Client("control_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
user_bot = Client("user_bot_session", session_string=USER_SESSION_STRING, in_memory=True)
admin_filter = filters.user(ADMIN_ID)

# --- Control Bot Commands ---
@control_bot.on_message(filters.command("start") & admin_filter)
async def start_command(client, message: Message):
    await message.reply_text("👋 **Stateless Forwarder Bot**\n\nI am online. Use `/bootstrap` to initialize storage if this is your first time.")

@control_bot.on_message(filters.command("bootstrap") & admin_filter)
async def bootstrap(client, message: Message):
    try:
        msg = await client.send_message(CONFIG_CHANNEL_ID, text=json.dumps({"forwards": {}}, indent=4))
        await client.pin_chat_message(CONFIG_CHANNEL_ID, msg.id, disable_notification=True)
        global config_message_id
        config_message_id = msg.id
        await message.reply_text(f"✅ Successfully bootstrapped config storage in channel `{CONFIG_CHANNEL_ID}`.")
    except Exception as e:
        await message.reply_text(f"❌ Failed to bootstrap. Is the bot an admin in the config channel with pin permissions? Error: {e}")

# (Your /add, /addsource, /delete, /list handlers go here...)

# --- Main Application Start ---
async def main():
    await control_bot.start()
    logger_control.info("Control Bot started.")

    if USER_SESSION_STRING:
        await user_bot.start()
        logger_user.info(f"UserBot started as {(await user_bot.get_me()).first_name}.")
    
    await asyncio.Event().wait()

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger_control.info("Starting application...")
    asyncio.run(main())