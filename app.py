# app.py (Hybrid Version with API-Managed Config)
import os
import asyncio
import threading
import json
import logging
import requests
from flask import Flask
from pyrogram import Client, filters, errors

# --- Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s')
logger_control = logging.getLogger('ControlBot')
logger_user = logging.getLogger('UserBot')

flask_app = Flask(__name__)
@flask_app.route('/')
def health_check(): return "Bot is alive and configurable!", 200
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
USER_SESSION_STRING = get_env('USER_SESSION_STRING', 'USER_SESSION_STRING not set!')

# Koyeb API configuration
KOYEB_API_TOKEN = get_env('KOYEB_API_TOKEN', 'KOYEB_API_TOKEN not set!')
KOYEB_SERVICE_ID = get_env('KOYEB_SERVICE_ID', 'KOYEB_SERVICE_ID not set!')
KOYEB_API_URL = f"https://app.koyeb.com/v1/services/{KOYEB_SERVICE_ID}"
KOYEB_HEADERS = {"Authorization": f"Bearer {KOYEB_API_TOKEN}", "Content-Type": "application/json"}

# --- Koyeb Config Management ---
def get_koyeb_config():
    try:
        response = requests.get(KOYEB_API_URL, headers=KOYEB_HEADERS)
        response.raise_for_status()
        service_definition = response.json().get("service", {}).get("definition", {})
        
        for env_var in service_definition.get("env", []):
            if env_var.get("key") == "FORWARD_CONFIG_JSON":
                return json.loads(env_var.get("value", "{}"))
        return {} # Return empty if not found
    except Exception as e:
        logger_control.error(f"Failed to get Koyeb config: {e}")
        return None

def update_koyeb_config(new_config_json):
    payload = {
        "definition": {
            "env": [
                {"key": "FORWARD_CONFIG_JSON", "value": json.dumps(new_config_json)}
            ]
        }
    }
    try:
        response = requests.patch(KOYEB_API_URL, headers=KOYEB_HEADERS, json=payload)
        response.raise_for_status()
        return True
    except Exception as e:
        logger_control.error(f"Failed to update Koyeb config: {e}")
        return False

# --- Pyrogram Clients ---
control_bot = Client("control_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
admin_filter = filters.user(ADMIN_ID)

# --- Control Bot Commands ---
@control_bot.on_message(filters.command("start") & admin_filter)
async def start_command(client, message: Message):
    await message.reply_text("👋 **Hybrid Forwarder Bot**\n\nI am online and ready. Use `/add`, `/delete`, and `/list` to manage forwarding rules. Each change will cause me to redeploy automatically.")

@control_bot.on_message(filters.command("add") & admin_filter)
async def add_forward(client, message: Message):
    parts = message.text.split()
    if len(parts) != 3: await message.reply_text("<b>Usage:</b> <code>/add <name> <dest_id></code>"); return
    _, name, dest_id_str = parts
    try: dest_id = int(dest_id_str)
    except ValueError: await message.reply_text("Destination ID must be a number."); return
    
    await message.reply_text("Fetching current config from Koyeb...")
    config = get_koyeb_config()
    if config is None: await message.reply_text("❌ Could not fetch config."); return
        
    if "forwards" not in config: config["forwards"] = {}
    config["forwards"][name] = {"destination": dest_id, "sources": []}
    
    await message.reply_text("Updating config on Koyeb and triggering redeploy...")
    if update_koyeb_config(config):
        await message.reply_text("✅ Success! Rule added. Please wait about a minute for me to restart with the new settings.")
    else:
        await message.reply_text("❌ Failed to update config on Koyeb.")

@control_bot.on_message(filters.command("addsource") & admin_filter)
async def add_source(client, message: Message):
    parts = message.text.split()
    if len(parts) < 3: await message.reply_text("<b>Usage:</b> <code>/addsource <name> <src_id>...</code>"); return
    _, name, *source_id_strs = parts
    
    config = get_koyeb_config()
    if config is None or "forwards" not in config or name not in config["forwards"]:
        await message.reply_text(f"❌ Rule '<code>{name}</code>' not found."); return

    new_sources = []
    for src_id in source_id_strs:
        try:
            config["forwards"][name]["sources"].append(int(src_id))
            new_sources.append(src_id)
        except ValueError:
            await message.reply_text(f"Skipping invalid source ID: {src_id}")

    if not new_sources: await message.reply_text("No valid new sources to add."); return
        
    if update_koyeb_config(config):
        await message.reply_text(f"✅ Success! Added sources to '<code>{name}</code>'. I am now restarting. Please wait.")
    else:
        await message.reply_text("❌ Failed to update config.")

@control_bot.on_message(filters.command("delete") & admin_filter)
async def delete_forward(client, message: Message):
    parts = message.text.split()
    if len(parts) != 2: await message.reply_text("<b>Usage:</b> <code>/delete <name></code>"); return
    _, name = parts

    config = get_koyeb_config()
    if config is None or "forwards" not in config or name not in config["forwards"]:
        await message.reply_text(f"❌ Rule '<code>{name}</code>' not found."); return
        
    del config["forwards"][name]
    
    if update_koyeb_config(config):
        await message.reply_text(f"✅ Success! Rule '<code>{name}</code>' deleted. I am now restarting.")
    else:
        await message.reply_text("❌ Failed to update config.")

@control_bot.on_message(filters.command("list") & admin_filter)
async def list_forwards(client, message: Message):
    config = get_koyeb_config()
    if config is None: await message.reply_text("❌ Could not fetch config."); return
    forwards = config.get("forwards", {})
    if not forwards: await message.reply_text("No rules configured. Use `/add` to create one."); return
    
    response = "📋 **Current Forwarding Rules:**\n\n"
    for name, rule in forwards.items():
        response += f"• <b>{name}</b> -> <code>{rule['destination']}</code>\n"
        response += f"  Sources: {', '.join(map(str, rule.get('sources', []))) or '(None)'}\n\n"
    await message.reply_text(response)

# --- Main Application Start ---
async def run_userbot():
    logger_user.info("Starting UserBot worker...")
    config_json = os.environ.get("FORWARD_CONFIG_JSON", "{}")
    try:
        # Get all source chats from the config
        forward_rules = json.loads(config_json).get("forwards", {})
        source_chats = [src for rule in forward_rules.values() for src in rule.get("sources", [])]
    except json.JSONDecodeError:
        logger_user.error("Invalid FORWARD_CONFIG_JSON, UserBot will not forward."); return

    user_bot = Client("user_bot_session", session_string=USER_SESSION_STRING, in_memory=True)

    @user_bot.on_message(filters.chat(source_chats) & ~filters.service if source_chats else filters.false)
    async def forwarder_handler(client, message):
        # The rules are fixed at startup, a redeploy is needed to update them
        for name, rule in forward_rules.items():
            if message.chat.id in rule.get("sources", []):
                await message.copy(rule["destination"])
                logger_user.info(f"Forwarded message from {message.chat.id} via rule '{name}'")
                break
    try:
        await user_bot.start()
        logger_user.info(f"UserBot started as {(await user_bot.get_me()).first_name}.")
        await asyncio.Event().wait() # Keep userbot running
    except Exception as e:
        logger_user.error(f"UserBot failed to start: {e}")

async def main():
    # Start the UserBot (forwarder) in a background task
    if USER_SESSION_STRING:
        asyncio.create_task(run_userbot())

    # Start the Control Bot
    await control_bot.start()
    logger_control.info("Control Bot started.")
    
    await asyncio.Event().wait() # Keep control bot running

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger_control.info("Starting application...")
    asyncio.run(main())