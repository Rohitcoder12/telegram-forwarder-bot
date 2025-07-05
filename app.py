# app.py (FINAL - Corrected Bot Interaction Logic)
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
    if not user_bot or not user_bot.is_connected:
        logger_user.error("UserBot is not connected, cannot load config.")
        return False
    try:
        # Get the single pinned message
        async for msg in user_bot.get_chat_history(CONFIG_CHANNEL_ID, limit=1):
            if msg.text and msg.text.startswith('{'):
                # Check if this is our config message, maybe check for a specific keyword in it
                config_message_id = msg.id
                config_cache = json.loads(msg.text)
                logger_control.info(f"Successfully loaded config from message {config_message_id}")
                return True
    except Exception as e:
        logger_user.error(f"UserBot could not read config channel history: {e}")
    logger_control.warning("Could not find a valid config message. Use /bootstrap.")
    return False

async def save_config(config_data):
    global config_message_id, config_cache
    if not user_bot or not user_bot.is_connected:
        logger_user.error("UserBot is not connected, cannot save config.")
        return False

    json_text = json.dumps(config_data, indent=4)
    if config_message_id:
        try:
            await user_bot.edit_message_text(CONFIG_CHANNEL_ID, config_message_id, json_text)
        except Exception as e:
            logger_control.error(f"UserBot failed to edit config message: {e}")
            return False
    else: # If no config message exists yet (bootstrapping)
        try:
            msg = await user_bot.send_message(CONFIG_CHANNEL_ID, json_text)
            # You might need to give userbot admin rights to pin
            # await user_bot.pin_chat_message(CONFIG_CHANNEL_ID, msg.id, disable_notification=True)
            config_message_id = msg.id
            logger_control.info(f"UserBot created new config message: {config_message_id}")
        except Exception as e:
            logger_control.error(f"UserBot failed to create config message: {e}")
            return False
            
    config_cache = config_data
    return True

# --- Control Bot Commands ---
@control_bot.on_message(filters.command("start") & admin_filter)
async def start_command(client, message):
    await message.reply_text("👋 **Forwarder Bot is Online**\n\n- The Userbot forwarder is running.\n- Use `/add` and other commands to manage rules.")

@control_bot.on_message(filters.command("bootstrap") & admin_filter)
async def bootstrap_command(client, message):
    msg = await message.reply_text("Attempting to create and pin a new config message in the config channel...")
    initial_config = {"forwards": {}}
    if await save_config(initial_config):
         await msg.edit_text("✅ Successfully created a new config message. You can now use `/add`.")
    else:
        await msg.edit_text("❌ Failed to create config message. Please check logs and ensure the user account (not the bot) is in the config channel.")

@control_bot.on_message(filters.command("add") & admin_filter)
async def add_forward(client, message):
    parts = message.text.split()
    if len(parts) != 3: await message.reply_text("<b>Usage:</b> <code>/add <name> <dest_id></code>"); return
    _, name, dest_id_str = parts; dest_id = int(dest_id_str)
    
    config = config_cache.copy()
    if "forwards" not in config: config["forwards"] = {}
    config["forwards"][name] = {"destination": dest_id, "sources": []}
    if await save_config(config):
        await message.reply_text(f"✅ Forward '<code>{name}</code>' created.")
    else:
        await message.reply_text("❌ Failed to save config.")

@control_bot.on_message(filters.command("addsource") & admin_filter)
async def add_source(client, message):
    parts = message.text.split()
    if len(parts) < 3: await message.reply_text("<b>Usage:</b> <code>/addsource <name> <src_id>...</code>"); return
    _, name, *source_id_strs = parts
    
    config = config_cache.copy()
    if name not in config.get("forwards", {}):
        await message.reply_text(f"❌ Rule '<code>{name}</code>' not found."); return
        
    for src_id in source_id_strs:
        config["forwards"][name]["sources"].append(int(src_id))
        
    if await save_config(config):
        await message.reply_text(f"✅ Sources added to '<code>{name}</code>'.")
    else:
        await message.reply_text("❌ Failed to save config.")

# (Add your /delete and /list handlers here, they follow the same `await save_config(config)` pattern)

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
async def main():
    if not user_bot:
        logger_control.critical("SESSION_STRING not set. Exiting.")
        return

    # Start both clients concurrently
    await asyncio.gather(
        user_bot.start(),
        control_bot.start()
    )
    
    logger_user.info(f"UserBot started as {(await user_bot.get_me()).first_name}.")
    await load_config() # Load the config using the now-active user_bot
    logger_control.info(f"Control Bot started as {(await control_bot.get_me()).first_name}.")
    
    await asyncio.Event().wait()

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger_control.info("Starting application...")
    asyncio.run(main())