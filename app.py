# app.py (FINAL ROBUST VERSION)
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
SESSION_STRING = get_env('SESSION_STRING', 'SESSION_STRING is optional', required=False)

config_message_id = None
config_cache = {"forwards": {}}

# --- Configuration Management (Telegram Channel) ---
async def get_config_message(client):
    global config_message_id
    if config_message_id:
        try:
            return await client.get_messages(CONFIG_CHANNEL_ID, config_message_id)
        except Exception:
            config_message_id = None
    try:
        async for msg in client.get_chat_history(CONFIG_CHANNEL_ID, limit=50):
             if msg.is_pinned and msg.text and msg.text.startswith('{'):
                 config_message_id = msg.id
                 return msg
    except Exception as e:
        logger_control.error(f"Could not search for config message: {e}")
    return None

async def load_config(client):
    global config_cache
    msg = await get_config_message(client)
    if msg and msg.text:
        try:
            config_cache = json.loads(msg.text)
            return True
        except json.JSONDecodeError:
            logger_control.error("Could not parse JSON from config message.")
    return False

async def save_config(client, config_data):
    global config_message_id
    if not config_message_id:
        await client.send_message(ADMIN_ID, "Error: Cannot save config, no bootstrap message found. Please use /bootstrap first.")
        return
    try:
        await client.edit_message_text(CONFIG_CHANNEL_ID, config_message_id, json.dumps(config_data, indent=4))
        global config_cache
        config_cache = config_data
    except FloodWait as e:
        await asyncio.sleep(e.x)
        await save_config(client, config_data)
    except Exception as e:
        logger_control.error(f"Failed to save config: {e}")

# --- Pyrogram Clients ---
control_bot = Client("control_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
user_bot = Client("user_bot_session", session_string=SESSION_STRING, in_memory=True) if SESSION_STRING else None
admin_filter = filters.user(ADMIN_ID)

# --- Control Bot Commands ---
@control_bot.on_message(filters.command("ping"))
async def ping_command(client, message: Message):
    await message.reply_text(f"Pong! I am alive.\nYour user ID is: <code>{message.from_user.id}</code>")

@control_bot.on_message(filters.command("start") & admin_filter)
async def start_command(client, message: Message):
    await message.reply_text("👋 **Forwarder Bot is Online**\n\nUse `/bootstrap` to initialize storage if this is your first time, then use `/add` and other commands.")

@control_bot.on_message(filters.command("bootstrap") & admin_filter)
async def bootstrap(client, message: Message):
    try:
        initial_config = {"forwards": {}}
        msg = await client.send_message(CONFIG_CHANNEL_ID, text=json.dumps(initial_config, indent=4))
        await client.pin_chat_message(CONFIG_CHANNEL_ID, msg.id, disable_notification=True)
        global config_message_id
        config_message_id = msg.id
        await message.reply_text(f"✅ Successfully bootstrapped config storage in channel `{CONFIG_CHANNEL_ID}`.")
    except Exception as e:
        await message.reply_text(f"❌ Failed to bootstrap. Is the bot an admin in the config channel? Error: {e}")

# (Add your /add, /addsource, /delete, /list handlers here...)

# --- Userbot Handler ---
@user_bot.on_message(~filters.service & filters.chat(list(config_cache.get("forwards", {}).keys())), group=1)
async def forwarder_handler(client, message: Message):
    forwards = config_cache.get("forwards", {})
    for name, rule in forwards.items():
        if message.chat.id in rule["sources"]:
            await message.copy(rule["destination"])
            break

# --- Main Application Start ---
async def start_bots():
    await control_bot.start()
    logger_control.info(f"Control Bot started as {(await control_bot.get_me()).first_name}.")
    
    # Load config after control bot is up
    if not await load_config(control_bot):
        logger_control.warning("Could not load initial config. Bot will still run, awaiting /bootstrap.")

    if user_bot:
        try:
            await user_bot.start()
            logger_user.info(f"UserBot started as {(await user_bot.get_me()).first_name}.")
        except Exception as e:
            logger_user.error(f"CRITICAL: UserBot failed to start. Is the SESSION_STRING valid? Error: {e}")
            # Notify the admin that the userbot failed
            await control_bot.send_message(ADMIN_ID, f"**WARNING:** The UserBot (forwarder) failed to start.\n\n**Reason:**\n`{e}`\n\nPlease check your `SESSION_STRING` variable. The control bot will continue to work.")
    else:
        logger_user.warning("SESSION_STRING not found. UserBot will not start.")
        
if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger_control.info("Starting application...")
    # Run the bot startup in the main asyncio loop
    control_bot.run(start_bots())