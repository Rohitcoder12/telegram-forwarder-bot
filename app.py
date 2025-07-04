# app.py (Stateless Version for Free Tier)
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
def get_env(name, message, cast=str, required=True):
    if name in os.environ:
        return cast(os.environ[name])
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

# This will hold the ID of our config message
config_message_id = None

# --- New Configuration Management (using Telegram Channel) ---
async def get_config_message_id(client):
    global config_message_id
    if config_message_id:
        return config_message_id
    
    # Search for a pinned message to use as our config
    try:
        async for msg in client.get_chat_history(CONFIG_CHANNEL_ID, limit=20):
             if msg.is_pinned:
                 config_message_id = msg.id
                 logger_control.info(f"Found pinned config message with ID: {config_message_id}")
                 return config_message_id
    except Exception as e:
        logger_control.error(f"Could not search for config message. Is the bot an admin in the config channel? Error: {e}")
        return None
    
    logger_control.warning("No pinned config message found. Use /bootstrap to create one.")
    return None

async def load_config(client):
    msg_id = await get_config_message_id(client)
    if not msg_id:
        return {}
    try:
        msg = await client.get_messages(CONFIG_CHANNEL_ID, msg_id)
        return json.loads(msg.text)
    except Exception as e:
        logger_control.error(f"Failed to load/parse config from message: {e}")
        return {}

async def save_config(client, config_data):
    msg_id = await get_config_message_id(client)
    if not msg_id:
        logger_control.error("Cannot save config, no config message ID found. Use /bootstrap.")
        return
    try:
        await client.edit_message_text(
            chat_id=CONFIG_CHANNEL_ID,
            message_id=msg_id,
            text=json.dumps(config_data, indent=4)
        )
    except Exception as e:
        logger_control.error(f"Failed to save config: {e}")

# --- Pyrogram Clients Setup ---
control_bot = Client("control_bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
user_bot = None
admin_filter = filters.user(ADMIN_ID)

# --- Control Bot Commands ---

@control_bot.on_message(filters.command("start") & admin_filter)
async def start_command(client, message: Message):
    await message.reply_text(
        "👋 **Stateless Forwarder Bot**\n\n"
        "1. First, create a config message with `/bootstrap`.\n"
        "2. If you don't have a user session string, get one with `/getsession`.\n"
        "3. Add the session string to the `USER_SESSION_STRING` env var on Koyeb.\n"
        "4. Use `/add`, `/list` etc. to manage forwards."
    )

@control_bot.on_message(filters.command("bootstrap") & admin_filter)
async def bootstrap(client, message: Message):
    """Creates the initial config message in the channel."""
    try:
        msg = await client.send_message(CONFIG_CHANNEL_ID, text=json.dumps({}, indent=4))
        await client.pin_chat_message(CONFIG_CHANNEL_ID, msg.id, disable_notification=True)
        global config_message_id
        config_message_id = msg.id
        await message.reply_text(f"✅ Successfully created and pinned config message with ID `{msg.id}` in your config channel.")
    except Exception as e:
        await message.reply_text(f"❌ Failed to bootstrap. Ensure the bot is an admin in the config channel with pin permissions. Error: {e}")

@control_bot.on_message(filters.command("getsession") & admin_filter)
async def get_session_command(client, message: Message):
    await message.reply_text(
        "This command will generate a session string.\n"
        "**WARNING:** The session will be sent here. It's recommended to delete these messages after use.\n\n"
        "Please send the phone number for the forwarding account (e.g., +11234567890)."
    )
    # This is a simplified, one-off login flow
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
    
    await message.reply_text(
        "✅ **Login successful!**\n\n"
        "Here is your session string. **Copy it carefully.**\n\n"
        "Go to your Koyeb dashboard -> Environment Variables, and create/update a secret variable named `USER_SESSION_STRING` with this value:\n\n"
        f"<code>{session_string}</code>\n\n"
        "After saving, the bot will restart and the forwarder will come online."
    )

# --- Task Management Commands ---
@control_bot.on_message(filters.command("add") & admin_filter)
async def add_forward(client, message: Message):
    parts = message.text.split()
    if len(parts) != 3: await message.reply_text("<b>Usage:</b> <code>/add <name> <dest_id></code>"); return
    _, name, dest_id_str = parts
    try: dest_id = int(dest_id_str)
    except ValueError: await message.reply_text("Dest ID must be a number."); return
    
    config = await load_config(client)
    if "forwards" not in config: config["forwards"] = {}
    config["forwards"][name] = {"destination": dest_id, "sources": []}
    await save_config(client, config)
    await message.reply_text(f"✅ Forward '<code>{name}</code>' created.")

@control_bot.on_message(filters.command("addsource") & admin_filter)
async def add_source(client, message: Message):
    parts = message.text.split()
    if len(parts) < 3: await message.reply_text("<b>Usage:</b> <code>/addsource <name> <src_id>...</code>"); return
    _, name, *source_id_strs = parts
    
    config = await load_config(client)
    if "forwards" not in config or name not in config["forwards"]:
        await message.reply_text(f"Forward '<code>{name}</code>' not found."); return
        
    for src_id_str in source_id_strs:
        config["forwards"][name]["sources"].append(int(src_id_str))
        
    await save_config(client, config)
    await message.reply_text(f"✅ Sources added to '<code>{name}</code>'.")

@control_bot.on_message(filters.command("list") & admin_filter)
async def list_forwards(client, message: Message):
    config = await load_config(client)
    forwards = config.get("forwards", {})
    if not forwards: await message.reply_text("No rules configured."); return
    
    response = "📋 **Forwarding Rules:**\n\n"
    for name, rule in forwards.items():
        response += f"• <b>{name}</b> -> <code>{rule.get('destination')}</code>\n"
        response += f"  Sources: {', '.join(map(str, rule.get('sources', []))) or '(None)'}\n\n"
    await message.reply_text(response)

# --- Userbot Worker Logic ---
async def manage_userbot():
    global user_bot
    if not USER_SESSION_STRING:
        logger_user.warning("USER_SESSION_STRING not set. Userbot will not start.")
        return

    logger_user.info("Starting UserBot with session string...")
    user_bot = Client("user_bot_session", session_string=USER_SESSION_STRING, in_memory=True)
    
    @user_bot.on_message(filters.private | filters.group, group=1)
    async def forwarder_handler(client, message):
        # We can't easily load config here without access to the control bot client.
        # This is a limitation. A better way would be an external DB.
        # For now, let's assume the userbot doesn't need real-time config updates.
        # A simple restart on Koyeb will make it read the latest config.
        pass # The logic needs to be added inside the main loop

    try:
        await user_bot.start()
        me = await user_bot.get_me()
        logger_user.info(f"UserBot logged in as {me.first_name}")
        
        # This is where the actual forwarding happens
        while True:
            # Re-load config periodically. This is inefficient but works.
            config = await load_config(control_bot) 
            # This is a conceptual problem - the userbot doesn't have the control_bot client.
            # We will solve this by simply not having real-time updates for the userbot.
            # A restart after changing config is required.
            await asyncio.sleep(3600) # Sleep for an hour

    except Exception as e:
        logger_user.error(f"UserBot failed to start: {e}")

# --- Main Application Start ---
async def main():
    await control_bot.start()
    logger_control.info("Control Bot started.")

    if USER_SESSION_STRING:
        logger_user.info("USER_SESSION_STRING found, starting UserBot manager.")
        # This is a simplified approach. The userbot forwarding logic needs to be run.
        # The original manage_userbot() has issues in a single-script context. Let's simplify.
        
        global user_bot
        user_bot = Client("user_bot_session", session_string=USER_SESSION_STRING, in_memory=True)
        
        @user_bot.on_message(group=1)
        async def forwarder_handler(client, message):
            config = await load_config(control_bot) # Load config using the active control_bot
            forwards = config.get("forwards", {})
            for name, rule in forwards.items():
                if message.chat.id in rule.get("sources", []):
                    dest = rule.get("destination")
                    logger_user.info(f"Forwarding from {message.chat.id} to {dest}")
                    try: await message.copy(dest)
                    except Exception as e: logger_user.error(f"Forward failed: {e}")
                    break
        
        await user_bot.start()
        logger_user.info(f"UserBot started as {(await user_bot.get_me()).first_name}")

    await asyncio.Event().wait()

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger_control.info("Starting application...")
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Application stopped.")