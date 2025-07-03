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

# The bot that handles commands
control_bot = Client("data/control_bot_session", bot_token=BOT_TOKEN)

# The userbot that does the forwarding. It will be initialized later.
user_bot = None

# --- Control Bot Command Handlers ---
admin_filter = filters.user(ADMIN_ID)

@control_bot.on_message(filters.command("login") & admin_filter)
async def login_start(client, message: Message):
    # ... (Login logic is identical to the previous controlbot.py) ...
    config = load_config()
    if config.get("user_session_string"):
        await message.reply_text("You are already logged in. Use `/logout` first.")
        return

    login_state[ADMIN_ID] = {"state": "awaiting_phone"}
    await message.reply_text("Please send the phone number for the forwarding account (e.g., +11234567890).")


@control_bot.on_message(filters.command("logout") & admin_filter)
async def logout(client, message: Message):
    # ... (Logout logic is identical to the previous controlbot.py) ...
    config = load_config()
    if "user_session_string" in config:
        del config["user_session_string"]
        save_config(config)
        await message.reply_text("✅ Logged out. The forwarder will stop. Use `/login` to start again.")
    else:
        await message.reply_text("You are not logged in.")

# --- Main Message Handler for Login Steps ---
@control_bot.on_message(filters.private & admin_filter & ~filters.command())
async def handle_login_steps(client, message: Message):
    # ... (This entire section is identical to the previous controlbot.py) ...
    if ADMIN_ID not in login_state: return
    state_data = login_state[ADMIN_ID]
    current_state = state_data.get("state")
    # Awaiting phone
    if current_state == "awaiting_phone":
        phone = message.text
        temp_client = Client(":memory:", api_id=API_ID, api_hash=API_HASH)
        try:
            await temp_client.connect()
            sent_code = await temp_client.send_code(phone)
            state_data.update({"state": "awaiting_otp", "phone": phone, "phone_code_hash": sent_code.phone_code_hash})
            await message.reply_text("OTP sent. Please send it here.")
        except Exception as e:
            await message.reply_text(f"Error: {e}"); del login_state[ADMIN_ID]
        finally: await temp_client.disconnect()
    # Awaiting OTP
    elif current_state == "awaiting_otp":
        otp = message.text
        temp_client = Client(":memory:", api_id=API_ID, api_hash=API_HASH)
        try:
            await temp_client.connect()
            await temp_client.sign_in(state_data["phone"], state_data["phone_code_hash"], otp)
            session_string = await temp_client.export_session_string()
            config = load_config(); config["user_session_string"] = session_string; save_config(config)
            await message.reply_text("✅ Login successful! Forwarder is starting."); del login_state[ADMIN_ID]
        except errors.SessionPasswordNeeded:
            state_data["state"] = "awaiting_password"; await message.reply_text("2FA password needed.")
        except Exception as e:
            await message.reply_text(f"Error: {e}"); del login_state[ADMIN_ID]
        finally: await temp_client.disconnect()
    # Awaiting Password
    elif current_state == "awaiting_password":
        password = message.text
        temp_client = Client(":memory:", api_id=API_ID, api_hash=API_HASH)
        try:
            await temp_client.connect()
            await temp_client.check_password(password)
            session_string = await temp_client.export_session_string()
            config = load_config(); config["user_session_string"] = session_string; save_config(config)
            await message.reply_text("✅ Login successful! Forwarder is starting."); del login_state[ADMIN_ID]
        except Exception as e:
            await message.reply_text(f"Error: {e}"); del login_state[ADMIN_ID]
        finally: await temp_client.disconnect()

# --- Task Management Commands (`/add`, `/list`, etc.) ---
# ... (Copy your `/add`, `/addsource`, `/delete`, `/list` handlers here) ...
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
    """This task manages the lifecycle of the userbot."""
    global user_bot
    while True:
        await asyncio.sleep(5) # Check config every 5 seconds
        config = load_config()
        session_string = config.get("user_session_string")

        if session_string and not user_bot:
            # If session exists and bot is not running, start it
            logger_user.info("Session string found. Starting UserBot...")
            user_bot = Client("data/user_bot_session", session_string=session_string)
            try:
                await user_bot.start()
                me = await user_bot.get_me()
                logger_user.info(f"UserBot logged in as {me.first_name} (@{me.username})")

                # Define the forwarding handler INSIDE the running client
                @user_bot.on_message(filters.private | filters.group, group=1)
                async def forwarder_handler(client, message):
                    current_config = load_config()
                    forwards = current_config.get("forwards", {})
                    for name, rule in forwards.items():
                        if message.chat.id in rule.get("sources", []):
                            dest = rule.get("destination")
                            logger_user.info(f"Forwarding from {message.chat.id} to {dest} (Rule: {name})")
                            try: await message.copy(dest)
                            except Exception as e: logger_user.error(f"Forward failed: {e}")
                            break
            
            except Exception as e:
                logger_user.error(f"Failed to start UserBot: {e}. Clearing session string.")
                config = load_config(); del config["user_session_string"]; save_config(config)
                user_bot = None

        elif not session_string and user_bot:
            # If session is gone and bot is running, stop it
            logger_user.info("Session string removed. Stopping UserBot...")
            await user_bot.stop()
            user_bot = None
            logger_user.info("UserBot stopped.")


# --- Main Application Start ---
async def main():
    # Start the control bot and the userbot manager concurrently
    await control_bot.start()
    logger_control.info("Control Bot started.")
    
    # Run the userbot manager as a background task
    asyncio.create_task(manage_userbot())
    
    # Keep the main process alive
    await asyncio.Event().wait()


if __name__ == "__main__":
    if not os.path.exists('data'): os.makedirs('data')
    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Run the main asyncio event loop
    logger_control.info("Starting application...")
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Application stopped.")