import os
import asyncio
import threading
from flask import Flask
from pyrogram import Client, filters
from pyrogram.errors import FloodWait

# --- Flask App for Health Checks ---
# This part is to keep the Koyeb Web Service alive.
flask_app = Flask(__name__)

@flask_app.route('/')
def health_check():
    return "Bot is alive and running!"

def run_flask():
    # Get the port from the environment variable KOYEB provides.
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)

# --- Pyrogram Bot Configuration ---

def get_env(name, message, cast=str):
    if name in os.environ:
        return cast(os.environ[name])
    print(message)
    exit(1)

API_ID = get_env('API_ID', 'Error: API_ID not found.', int)
API_HASH = get_env('API_HASH', 'Error: API_HASH not found.')
SESSION_NAME = "data/my_forwarder_session"
source_chats_str = get_env('SOURCE_CHATS', 'Error: SOURCE_CHATS not found.')
try:
    SOURCE_CHATS = [int(x.strip()) for x in source_chats_str.split(',')]
except ValueError:
    print("Error: SOURCE_CHATS must be a comma-separated list of numbers.")
    exit(1)

DESTINATION_CHANNEL = get_env('DESTINATION_CHANNEL', 'Error: DESTINATION_CHANNEL not found.', int)

# --- Pyrogram Bot Logic ---
app = Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH)

@app.on_message(filters.chat(SOURCE_CHATS) & filters.incoming)
async def forward_message(client, message):
    print(f"Detected message from {message.chat.id}. Forwarding...")
    try:
        await message.copy(DESTINATION_CHANNEL)
        print("Message forwarded successfully!")
    except FloodWait as e:
        print(f"FloodWait: Waiting for {e.x} seconds.")
        await asyncio.sleep(e.x)
        await message.copy(DESTINATION_CHANNEL)
        print("Message forwarded after waiting.")
    except Exception as e:
        print(f"An error occurred while forwarding: {e}")

async def run_pyrogram():
    print("Starting the forwarder bot...")
    await app.start()
    print("Bot is running.")
    await asyncio.Event().wait()

# --- Main Execution ---
if __name__ == "__main__":
    # Create the 'data' directory if it doesn't exist
    if not os.path.exists('data'):
        os.makedirs('data')

    # Start the Flask server in a separate thread
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # Run the Pyrogram client
    try:
        asyncio.run(run_pyrogram())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped.")