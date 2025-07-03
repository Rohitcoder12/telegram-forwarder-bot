import os
import asyncio
import threading
import json
import logging
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait

# --- Basic Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Flask App for Health Checks (for Koyeb Web Service) ---
flask_app = Flask(__name__)

@flask_app.route('/')
def health_check():
    return "Configuration bot is alive!", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)

# --- Configuration Management ---
CONFIG_FILE_PATH = "data/config.json"

def get_env(name, message, cast=str, required=True):
    if name in os.environ:
        return cast(os.environ[name])
    if required:
        logger.error(message)
        exit(1)
    return None

def load_config():
    """Loads the configuration from the JSON file."""
    if os.path.exists(CONFIG_FILE_PATH):
        with open(CONFIG_FILE_PATH, 'r') as f:
            return json.load(f)
    return {}

def save_config(config):
    """Saves the configuration to the JSON file."""
    with open(CONFIG_FILE_PATH, 'w') as f:
        json.dump(config, f, indent=4)

# --- Pyrogram Bot Setup ---
API_ID = get_env('API_ID', 'Error: API_ID not found.', int)
API_HASH = get_env('API_HASH', 'Error: API_HASH not found.')
ADMIN_ID = get_env('ADMIN_ID', 'Error: ADMIN_ID not found.', int)

app = Client("data/my_forwarder_session", api_id=API_ID, api_hash=API_HASH)

# In-memory representation of the config for quick lookups
config_cache = load_config()

# --- Command Handlers (Admin Only) ---
admin_filter = filters.user(ADMIN_ID)

@app.on_message(filters.command("add") & admin_filter)
async def add_forward(client, message: Message):
    """Adds a new forwarding rule. Usage: /add <forward_name> <destination_id>"""
    parts = message.text.split()
    if len(parts) != 3:
        await message.reply_text("<b>Usage:</b> <code>/add <forward_name> <destination_id></code>\n\n"
                                 "Example: <code>/add my_crypto_news -1001234567890</code>")
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
    await message.reply_text(f"✅ Forward '<code>{name}</code>' created successfully.\n"
                             f"Now add source chats with:\n<code>/addsource {name} <source_id_1> <source_id_2>...</code>")

@app.on_message(filters.command("addsource") & admin_filter)
async def add_source(client, message: Message):
    """Adds source chats to an existing forwarding rule."""
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
        await message.reply_text(f"✅ Added sources to '<code>{name}</code>':\n<code>" + "\n".join(added_sources) + "</code>")
    else:
        await message.reply_text("No new sources were added (either invalid or already exist).")


@app.on_message(filters.command("delete") & admin_filter)
async def delete_forward(client, message: Message):
    """Deletes a forwarding rule completely."""
    parts = message.text.split()
    if len(parts) != 2:
        await message.reply_text("<b>Usage:</b> <code>/delete <forward_name></code>")
        return
    
    _, name = parts
    if name not in config_cache:
        await message.reply_text(f"Error: No forward found with the name '<code>{name}</code>'.")
        return
        
    del config_cache[name]
    save_config(config_cache)
    await message.reply_text(f"🗑️ Forward '<code>{name}</code>' has been deleted.")


@app.on_message(filters.command("list") & admin_filter)
async def list_forwards(client, message: Message):
    """Lists all current forwarding configurations."""
    if not config_cache:
        await message.reply_text("No forwarding rules are configured yet.")
        return

    response = "📋 **Current Forwarding Rules:**\n\n"
    for name, config in config_cache.items():
        response += f"• **Name:** <code>{name}</code>\n"
        response += f"  - **Destination:** <code>{config['destination']}</code>\n"
        response += f"  - **Sources:**\n"
        if config['sources']:
            for src in config['sources']:
                response += f"    - <code>{src}</code>\n"
        else:
            response += "    - (No sources yet)\n"
        response += "\n"
    
    await message.reply_text(response)

@app.on_message(filters.command("help") & admin_filter)
async def help_command(client, message: Message):
    help_text = """
    **Bot Commands Help**

    `/add <name> <dest_id>`
    Creates a new forward rule.
    _e.g., /add project_updates -100123456_

    `/addsource <name> <src_id_1> <src_id_2>...`
    Adds one or more source chats to a rule.
    _e.g., /addsource project_updates -100789 -100456_

    `/delete <name>`
    Deletes an entire forward rule.
    _e.g., /delete project_updates_

    `/list`
    Shows all configured forward rules.

    `/help`
    Displays this message.

    **How to get Chat IDs?**
    Forward a message from the target chat to a bot like `@userinfobot` to get its ID.
    """
    await message.reply_text(help_text)


# --- Core Forwarding Logic ---
@app.on_message(filters.private & filters.incoming)
async def main_forwarder(client: Client, message: Message):
    # Ignore commands from admin to prevent self-forwarding
    if message.from_user and message.from_user.id == ADMIN_ID and message.text.startswith('/'):
        return

    chat_id = message.chat.id
    
    # Check against the cached config
    for name, config in config_cache.items():
        if chat_id in config["sources"]:
            destination = config["destination"]
            logger.info(f"Forwarding from source {chat_id} to destination {destination} (Rule: {name})")
            try:
                await message.copy(destination)
            except FloodWait as e:
                logger.warning(f"FloodWait: Waiting for {e.x} seconds.")
                await asyncio.sleep(e.x)
                await message.copy(destination) # Retry
            except Exception as e:
                logger.error(f"Could not forward message: {e}")
            # Break after finding the first matching rule to avoid multiple forwards
            break

# --- Main Execution ---
async def run_pyrogram():
    logger.info("Starting the forwarder bot...")
    await app.start()
    logger.info("Bot is running.")
    await asyncio.Event().wait()

if __name__ == "__main__":
    if not os.path.exists('data'):
        os.makedirs('data')
    
    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # Run Pyrogram client
    try:
        asyncio.run(run_pyrogram())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")