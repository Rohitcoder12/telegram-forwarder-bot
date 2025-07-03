# controlbot.py
import os
import threading
import json
import logging
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import Message

# --- Basic Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [ControlBot] - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Flask App for Health Checks ---
flask_app = Flask(__name__)
@flask_app.route('/')
def health_check():
    return "Control Bot is alive!", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)

# --- Configuration Management ---
CONFIG_FILE_PATH = "data/config.json"

def get_env(name, message, cast=str):
    if name in os.environ:
        return cast(os.environ[name])
    logger.error(message)
    exit(1)

def load_config():
    if os.path.exists(CONFIG_FILE_PATH):
        with open(CONFIG_FILE_PATH, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_config(config):
    with open(CONFIG_FILE_PATH, 'w') as f:
        json.dump(config, f, indent=4)

# --- Pyrogram Control Bot Setup ---
BOT_TOKEN = get_env('BOT_TOKEN', 'Error: BOT_TOKEN not found.')
ADMIN_ID = get_env('ADMIN_ID', 'Error: ADMIN_ID not found.', int)

app = Client("data/my_control_bot", bot_token=BOT_TOKEN)

# --- Command Handlers ---
admin_filter = filters.user(ADMIN_ID)

@app.on_message(filters.command("add") & admin_filter)
async def add_forward(client, message: Message):
    config_cache = load_config()
    parts = message.text.split()
    if len(parts) != 3:
        await message.reply_text("<b>Usage:</b> <code>/add <forward_name> <destination_id></code>")
        return
    
    _, name, dest_id_str = parts
    try:
        dest_id = int(dest_id_str)
    except ValueError:
        await message.reply_text("Error: Destination ID must be a number.")
        return

    if name in config_cache:
        await message.reply_text(f"Error: A forward with the name '<code>{name}</code>' already exists.")
        return

    config_cache[name] = {"destination": dest_id, "sources": []}
    save_config(config_cache)
    await message.reply_text(f"✅ Forward '<code>{name}</code>' created. Add sources with:\n<code>/addsource {name} <source_id></code>")

@app.on_message(filters.command("addsource") & admin_filter)
async def add_source(client, message: Message):
    config_cache = load_config()
    parts = message.text.split()
    if len(parts) < 3:
        await message.reply_text("<b>Usage:</b> <code>/addsource <forward_name> <source_id_1> [source_id_2]...</code>")
        return

    _, name, *source_id_strs = parts
    if name not in config_cache:
        await message.reply_text(f"Error: No forward found with the name '<code>{name}</code>'.")
        return

    added_sources = []
    for src_id_str in source_id_strs:
        try:
            src_id = int(src_id_str)
            if src_id not in config_cache[name]["sources"]:
                config_cache[name]["sources"].append(src_id)
                added_sources.append(str(src_id))
        except ValueError:
            await message.reply_text(f"Skipping invalid source ID: '{src_id_str}'")

    if added_sources:
        save_config(config_cache)
        await message.reply_text(f"✅ Added sources to '<code>{name}</code>'.")
    else:
        await message.reply_text("No new sources were added.")

@app.on_message(filters.command("delete") & admin_filter)
async def delete_forward(client, message: Message):
    config_cache = load_config()
    parts = message.text.split()
    if len(parts) != 2:
        await message.reply_text("<b>Usage:</b> <code>/delete <forward_name></code>")
        return
    
    _, name = parts
    if name in config_cache:
        del config_cache[name]
        save_config(config_cache)
        await message.reply_text(f"🗑️ Forward '<code>{name}</code>' deleted.")
    else:
        await message.reply_text(f"Error: No forward found with the name '<code>{name}</code>'.")

@app.on_message(filters.command("list") & admin_filter)
async def list_forwards(client, message: Message):
    config_cache = load_config()
    if not config_cache:
        await message.reply_text("No forwarding rules are configured.")
        return

    response = "📋 **Current Forwarding Rules:**\n\n"
    for name, config in config_cache.items():
        response += f"• <b>Name:</b> <code>{name}</code>\n"
        response += f"  - <b>Destination:</b> <code>{config['destination']}</code>\n"
        response += f"  - <b>Sources:</b> {', '.join(map(str, config.get('sources', []))) or '(None)'}\n\n"
    await message.reply_text(response)

# --- Main Execution ---
if __name__ == "__main__":
    if not os.path.exists('data'):
        os.makedirs('data')
    
    # Start Flask in a separate thread for health checks
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # Run the control bot
    logger.info("Starting the Control Bot (Manager)...")
    app.run()
    logger.info("Control bot stopped.")