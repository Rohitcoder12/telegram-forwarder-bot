# app.py
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

# --- Config and State Management ---
CONFIG_FILE_PATH = "data/config.json"
login_state = {}

def get_env(name, message, cast=str):
    if name in os.environ:
        return cast(os.environ[name])
    logging.critical(message)
    exit(1)

def load_config():
    if not os.path.exists(CONFIG_FILE_PATH): return {}
    with open(CONFIG_FILE_PATH, 'r') as f:
        try: return json.load(f)
        except json.JSONDecodeError: return {}

def save_config(config):
    with open(CONFIG_FILE_PATH, 'w') as f:
        json.dump(config, f, indent=4)

# --- Pyrogram Clients Setup ---
API_ID = get_env('API_ID', 'API_ID not set.', int)
API_HASH = get_env('API_HASH', 'API_HASH not set.')
BOT_TOKEN = get_env('BOT_TOKEN', 'BOT_TOKEN not set.')
ADMIN_ID = get_env('ADMIN_ID', 'ADMIN_ID not set.', int)

# THIS IS THE CORRECTED INITIALIZATION
control_bot = Client(
    "data/control_bot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

user_bot = None
admin_filter = filters.user(ADMIN_ID)

# --- Control Bot Command Handlers ---

@control_bot.on_message(filters.command("login") & admin_filter)
async def login_start(client, message: Message):
    config = load_config()
    if config.get("user_session_string"):
        await message.reply_text("You are already logged in. Use `/logout` first if you want to switch accounts.")
        return

    login_state[ADMIN_ID] = {"state": "awaiting_phone"}
    await message.reply_text("Please send the phone number of the account you want to use for forwarding (in international format, e.g., +11234567890).")

@control_bot.on_message(filters.command("logout") & admin_filter)
async def logout(client, message: Message):
    config = load_config()
    if "user_session_string" in config:
        del config["user_session_string"]
        save_config(config)
        await message.reply_text("✅ You have been successfully logged out. The forwarder will stop.\nUse `/login` to start again.")
    else:
        await message.reply_text("You are not logged in.")

# --- Main Message Handler for Login Steps ---
@control_bot.on_message(
    filters.text &
    filters.private &
    admin_filter &
    ~filters.command(["login", "logout", "add", "addsource", "delete", "list"])
)
async def handle_login_steps(client, message: Message):
    if ADMIN_ID not in login_state: return
    state_data = login_state[ADMIN_ID]
    current_state = state_data.get("state")

    if current_state == "awaiting_phone":
        phone = message.text
        temp_client = Client(":memory:", api_id=API_ID, api_hash=API_HASH)
        try:
            await temp_client.connect()
            sent_code = await temp_client.send_code(phone)
            state_data.update({"state": "awaiting_otp", "phone": phone, "phone_code_hash": sent_code.phone_code_hash})
            await message.reply_text("An OTP has been sent to your Telegram account. Please send it here.")
        except Exception as e:
            await message.reply_text(f"Error during login: {e}"); del login_state[ADMIN_ID]
        finally:
            await temp_client.disconnect()

    elif current_state == "awaiting_otp":
        otp = message.text
        temp_client = Client(":memory:", api_id=API_ID, api_hash=API_HASH)
        try:
            await temp_client.connect()
            await temp_client.sign_in(state_data["phone"], state_data["phone_code_hash"], otp)
            session_string = await temp_client.export_session_string()
            config = load_config(); config["user_session_string"] = session_string; save_config(config)
            await message.reply_text("✅ Login successful! The forwarder is starting."); del login_state[ADMIN_ID]
        except errors.SessionPasswordNeeded:
            state_data["state"] = "awaiting_password"; await message.reply_text("Your account has Two-Step Verification enabled. Please send your password.")
        except Exception as e:
            await message.reply_text(f"Error during login: {e}"); del login_state[ADMIN_ID]
        finally:
            await temp_client.disconnect()

    elif current_state == "awaiting_password":
        password = message.text
        temp_client = Client(":memory:", api_id=API_ID, api_hash=API_HASH)
        try:
            await temp_client.connect()
            await temp_client.check_password(password)
            session_string = await temp_client.export_session_string()
            config = load_config(); config["user_session_string"] = session_string; save_config(config)
            await message.reply_text("✅ Login successful! The forwarder is starting."); del login_state[ADMIN_ID]
        except Exception as e:
            await message.reply_text(f"Error during login: {e}"); del login_state[ADMIN_ID]
        finally:
            await temp_client.disconnect()

# --- Task Management Commands ---

@control_bot.on_message(filters.command("add") & admin_filter)
async def add_forward(client, message: Message):
    parts = message.text.split()
    if len(parts) != 3:
        await message.reply_text("<b>Usage:</b> <code>/add <forward_name> <destination_id></code>")
        return
    _, name, dest_id_str = parts
    try: dest_id = int(dest_id_str)
    except ValueError: await message.reply_text("Error: Destination ID must be a number."); return

    config = load_config()
    if "forwards" not in config: config["forwards"] = {}
    if name in config["forwards"]:
        await message.reply_text(f"Error: A forward with the name '<code>{name}</code>' already exists.")
        return
    config["forwards"][name] = {"destination": dest_id, "sources": []}
    save_config(config)
    await message.reply_text(f"✅ Forward '<code>{name}</code>' created. Add sources with:\n<code>/addsource {name} <source_id></code>")

@control_bot.on_message(filters.command("addsource") & admin_filter)
async def add_source(client, message: Message):
    parts = message.text.split()
    if len(parts) < 3:
        await message.reply_text("<b>Usage:</b> <code>/addsource <forward_name> <source_id_1> [source_id_2]...</code>")
        return
    _, name, *source_id_strs = parts
    config = load_config()
    if "forwards" not in config or name not in config["forwards"]:
        await message.reply_text(f"Error: No forward found with the name '<code>{name}</code>'.")
        return

    added_sources = []
    for src_id_str in source_id_strs:
        try:
            src_id = int(src_id_str)
            if src_id not in config["forwards"][name]["sources"]:
                config["forwards"][name]["sources"].append(src_id)
                added_sources.append(str(src_id))
        except ValueError: await message.reply_text(f"Skipping invalid source ID: '{src_id_str}'")

    if added_sources:
        save_config(config)
        await message.reply_text(f"✅ Added sources to '<code>{name}</code>':\n<code>" + ", ".join(added_sources) + "</code>")
    else: await message.reply_text("No new sources were added (either invalid or already exist).")

@control_bot.on_message(filters.command("delete") & admin_filter)
async def delete_forward(client, message: Message):
    parts = message.text.split()
    if len(parts) != 2: await message.reply_text("<b>Usage:</b> <code>/delete <forward_name></code>"); return
    _, name = parts
    config = load_config()
    if "forwards" in config and name in config["forwards"]:
        del config["forwards"][name]
        save_config(config)
        await message.reply_text(f"🗑️ Forward '<code>{name}</code>' has been deleted.")
    else: await message.reply_text(f"Error: No forward found with the name '<code>{name}</code>'.")

@control_bot.on_message(filters.command("list") & admin_filter)
async def list_forwards(client, message: Message):
    config = load_config()
    forwards = config.get("forwards", {})
    if not forwards:
        await message.reply_text("No forwarding rules are configured. Use `/add` to create one.")
        return
    
    response = "📋 **Current Forwarding Rules:**\n\n"
    for name, rule in forwards.items():
        response += f"• <b>Name:</b> <code>{name}</code>\n"
        response += f"  - <b>Destination:</b> <code>{rule.get('destination')}</code>\n"
        response += f"  - <b>Sources:</b> {', '.join(map(str, rule.get('sources', []))) or '(None)'}\n\n"
    await message.reply_text(response)


# --- Userbot Forwarding Logic ---
async def manage_userbot():
    global user_bot
    while True:
        await asyncio.sleep(5)
        config = load_config()
        session_string = config.get("user_session_string")

        if session_string and not user_bot:
            logger_user.info("Session string found. Starting UserBot...")
            user_bot = Client("data/user_bot_session", session_string=session_string)
            try:
                await user_bot.start()
                me = await user_bot.get_me()
                logger_user.info(f"UserBot logged in as {me.first_name} (@{me.username})")

                @user_bot.on_message(filters.private | filters.group, group=1)
                async def forwarder_handler(client, message):
                    current_config = load_config()
                    forwards = current_config.get("forwards", {})
                    for name, rule in forwards.items():
                        if message.chat.id in rule.get("sources", []):
                            dest = rule.get("destination")
                            if not dest: continue
                            logger_user.info(f"Forwarding from {message.chat.id} to {dest} (Rule: {name})")
                            try: await message.copy(dest)
                            except Exception as e: logger_user.error(f"Forward failed: {e}")
                            break
            except Exception as e:
                logger_user.error(f"Failed to start UserBot: {e}. Clearing session string.")
                config = load_config();
                if "user_session_string" in config:
                    del config["user_session_string"]
                save_config(config)
                user_bot = None

        elif not session_string and user_bot:
            logger_user.info("Session string removed. Stopping UserBot...")
            await user_bot.stop()
            user_bot = None
            logger_user.info("UserBot stopped.")


# --- Main Application Start ---
async def main():
    await control_bot.start()
    logger_control.info("Control Bot started.")
    asyncio.create_task(manage_userbot())
    await asyncio.Event().wait()


if __name__ == "__main__":
    if not os.path.exists('data'): os.makedirs('data')
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger_control.info("Starting application...")
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Application stopped.")