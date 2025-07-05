# app.py (FINAL - Corrected Startup Logic)
import os
import asyncio
import threading
import json
import logging
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait

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
CONFIG_CHANNEL_ID = get_env('CONFIG_CHANNEL_ID', 'CONFIG_CHANNEL_ID not set!', cast=int)
SESSION_STRING = get_env('SESSION_STRING', 'SESSION_STRING is optional', required=False)

config_message_id = None
config_cache = {"forwards": {}}

# --- Pyrogram Clients ---
control_bot = Client("control_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
user_bot = Client("user_bot_session", session_string=SESSION_STRING, api_id=API_ID, api_hash=API_HASH, in_memory=True) if SESSION_STRING else None
admin_filter = filters.user(ADMIN_ID)

# --- Configuration Management (These now require the user_bot client) ---
async def load_config():
    global config_message_id, config_cache
    if not user_bot or not user_bot.is_connected: return False
    try:
        async for msg in user_bot.get_chat_history(CONFIG_CHANNEL_ID, limit=50):
            if msg.text and msg.text.startswith('{'):
                config_message_id = msg.id
                config_cache = json.loads(msg.text)
                logger_control.info(f"Loaded config from message {config_message_id}")
                return True
    except Exception as e:
        logger_user.error(f"UserBot could not read config channel: {e}")
    return False

async def save_config(config_data):
    global config_message_id, config_cache
    if not user_bot or not user_bot.is_connected: return False

    json_text = json.dumps(config_data, indent=4)
    if config_message_id:
        try:
            await user_bot.edit_message_text(CONFIG_CHANNEL_ID, config_message_id, json_text)
        except Exception as e:
            logger_control.error(f"UserBot failed to edit config message: {e}"); return False
    else:
        try:
            msg = await user_bot.send_message(CONFIG_CHANNEL_ID, json_text)
            # Pinning is not essential for the logic to work, so we can omit it if it causes issues.
            # await user_bot.pin_chat_message(CONFIG_CHANNEL_ID, msg.id, disable_notification=True)
            config_message_id = msg.id
            logger_control.info(f"UserBot created new config message: {config_message_id}")
        except Exception as e:
            logger_control.error(f"UserBot failed to create config message: {e}"); return False
            
    config_cache = config_data
    return True

# --- Control Bot Commands ---
@control_bot.on_message(filters.command("start") & admin_filter)
async def start_command(client, message):
    await message.reply_text("👋 **Forwarder Bot is Online**\n\n- The Userbot forwarder is running.\n- Use `/bootstrap` to initialize storage if needed.\n- Use `/add` and other commands to manage rules.")

@control_bot.on_message(filters.command("bootstrap") & admin_filter)
async def bootstrap_command(client, message):
    msg = await message.reply_text("Attempting to create a new config message...")
    initial_config = {"forwards": {}}
    if await save_config(initial_config):
         await msg.edit_text("✅ Successfully created a new config message. You can now use `/add`.")
    else:
        await msg.edit_text("❌ Failed to create config message. Please check logs and ensure the user account is in the config channel.")

# (Add your /add, /addsource, /delete, /list handlers here...)

# --- Userbot Handler ---
@user_bot.on_message(~filters.service, group=1)
async def forwarder_handler(client, message):
    forwards = config_cache.get("forwards", {})
    if not forwards: return
    for name, rule in forwards.items():
        if message.chat.id in rule.get("sources", []):
            await message.copy(rule["destination"])
            break

# --- Main Application Start ---
if __name__ == "__main__":
    # Start the Flask server in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger_control.info("Starting application...")

    # Use the built-in run method which handles the event loop correctly
    if user_bot:
        user_bot.start()
        logger_user.info("UserBot instance started.")
        # Load the config right after userbot starts
        loop = asyncio.get_event_loop()
        loop.run_until_complete(load_config())
    
    control_bot.run()
    logger_control.info("Control Bot has stopped.")