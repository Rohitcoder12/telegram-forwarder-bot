# app.py (FINAL - Hybrid "Telegram as Database" Version)
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
def health_check(): return "Bot is alive and configurable!", 200
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
config_cache = {"forwards": {}} # In-memory cache

# --- Configuration Management (Telegram Channel) ---
async def load_config(userbot_client):
    global config_message_id, config_cache
    try:
        async for msg in userbot_client.get_chat_history(CONFIG_CHANNEL_ID, limit=50):
             if msg.is_pinned and msg.text and msg.text.startswith('{'):
                 config_message_id = msg.id
                 config_cache = json.loads(msg.text)
                 logger_control.info(f"Successfully loaded config from pinned message {config_message_id}")
                 return
    except Exception as e:
        logger_user.error(f"UserBot could not read config channel history: {e}")
    logger_control.warning("Could not find a valid pinned config message.")

async def save_config(userbot_client, config_data):
    global config_message_id, config_cache
    if not config_message_id:
        try:
            msg = await userbot_client.send_message(CONFIG_CHANNEL_ID, text=json.dumps(config_data, indent=4))
            await userbot_client.pin_chat_message(CONFIG_CHANNEL_ID, msg.id, disable_notification=True)
            config_message_id = msg.id
            logger_control.info(f"UserBot bootstrapped and pinned new config message: {config_message_id}")
        except Exception as e:
            logger_control.error(f"UserBot failed to bootstrap config message: {e}")
            return
    else:
        try:
            await userbot_client.edit_message_text(CONFIG_CHANNEL_ID, config_message_id, json.dumps(config_data, indent=4))
        except FloodWait as e:
            await asyncio.sleep(e.x)
            await save_config(userbot_client, config_data)
        except Exception as e:
            logger_control.error(f"UserBot failed to save config: {e}")
    config_cache = config_data

# --- Pyrogram Clients ---
control_bot = Client("control_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
user_bot = Client("user_bot_session", session_string=SESSION_STRING, in_memory=True) if SESSION_STRING else None
admin_filter = filters.user(ADMIN_ID)

# --- Control Bot Commands ---
@control_bot.on_message(filters.command("start") & admin_filter)
async def start_command(client, message):
    await message.reply_text("👋 **Forwarder Bot is Online**\n\n- The Userbot forwarder is running.\n- Use `/add` and other commands to manage rules.\n- Changes take effect instantly.")

@control_bot.on_message(filters.command("add") & admin_filter)
async def add_forward(client, message):
    parts = message.text.split()
    if len(parts) != 3: await message.reply_text("<b>Usage:</b> <code>/add <name> <dest_id></code>"); return
    _, name, dest_id_str = parts; dest_id = int(dest_id_str)
    
    config = config_cache.copy()
    if "forwards" not in config: config["forwards"] = {}
    config["forwards"][name] = {"destination": dest_id, "sources": []}
    await save_config(user_bot, config)
    await message.reply_text(f"✅ Forward '<code>{name}</code>' created. Now add sources with <code>/addsource {name} <id></code>.")

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
        
    await save_config(user_bot, config)
    await message.reply_text(f"✅ Sources added to '<code>{name}</code>'.")

@control_bot.on_message(filters.command("delete") & admin_filter)
async def delete_forward(client, message):
    parts = message.text.split()
    if len(parts) != 2: await message.reply_text("<b>Usage:</b> <code>/delete <name></code>"); return
    _, name = parts

    config = config_cache.copy()
    if name in config.get("forwards", {}):
        del config["forwards"][name]
        await save_config(user_bot, config)
        await message.reply_text(f"🗑️ Rule '<code>{name}</code>' deleted.")
    else:
        await message.reply_text(f"❌ Rule '<code>{name}</code>' not found.")

@control_bot.on_message(filters.command("list") & admin_filter)
async def list_forwards(client, message):
    forwards = config_cache.get("forwards", {})
    if not forwards: await message.reply_text("No rules configured."); return
    
    response = "📋 **Current Forwarding Rules:**\n\n"
    for name, rule in forwards.items():
        response += f"• <b>{name}</b> -> <code>{rule['destination']}</code>\n"
        response += f"  Sources: {', '.join(map(str, rule.get('sources', []))) or '(None)'}\n\n"
    await message.reply_text(response)

# --- Userbot Handler ---
@user_bot.on_message(~filters.service, group=1)
async def forwarder_handler(client, message):
    # Use the in-memory cache for speed
    forwards = config_cache.get("forwards", {})
    if not forwards: return
    
    # Check if the message is from any of our configured source chats
    for name, rule in forwards.items():
        if message.chat.id in rule.get("sources", []):
            try:
                await message.copy(rule["destination"])
                logger_user.info(f"Forwarded message from {message.chat.id} via rule '{name}'")
            except Exception as e:
                logger_user.error(f"Failed to forward message from {message.chat.id}: {e}")
            break # Stop after the first matching rule

# --- Main Application Start ---
async def main():
    if not user_bot:
        logger_control.critical("SESSION_STRING not set. The bot cannot function without it. Exiting.")
        return

    logger_control.info("Starting bots...")
    await user_bot.start()
    logger_user.info(f"UserBot started as {(await user_bot.get_me()).first_name}.")
    
    # Load the initial config using the now-active user_bot
    await load_config(user_bot)
    
    await control_bot.start()
    logger_control.info(f"Control Bot started as {(await control_bot.get_me()).first_name}.")
    
    await asyncio.Event().wait() # Keep everything running

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger_control.info("Starting application...")
    asyncio.run(main())