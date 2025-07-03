import os
import asyncio
import re
from pyrogram import Client, filters
from pyrogram.errors import FloodWait

# --- CONFIGURATION ---

# Function to safely get environment variables
def get_env(name, message, cast=str):
    if name in os.environ:
        return cast(os.environ[name])
    print(message)
    exit(1)

# Get configuration from environment variables
API_ID = get_env('API_ID', 'Error: API_ID not found in environment variables.', int)
API_HASH = get_env('API_HASH', 'Error: API_HASH not found in environment variables.')

# We will store the session file in a 'data' directory, which we will mount on Koyeb
SESSION_NAME = "data/my_forwarder_session"

# Source chats are now a comma-separated string in env variables
source_chats_str = get_env('SOURCE_CHATS', 'Error: SOURCE_CHATS not found.')
# Convert the comma-separated string of IDs into a list of integers
try:
    SOURCE_CHATS = [int(x.strip()) for x in source_chats_str.split(',')]
except ValueError:
    print("Error: SOURCE_CHATS must be a comma-separated list of numbers.")
    exit(1)

DESTINATION_CHANNEL = get_env('DESTINATION_CHANNEL', 'Error: DESTINATION_CHANNEL not found.', int)

# --- INITIALIZATION ---
app = Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH)

# --- THE FORWARDING LOGIC ---
@app.on_message(filters.chat(SOURCE_CHATS) & filters.incoming)
async def forward_message(client, message):
    print(f"Detected message from {message.chat.id}. Forwarding...")
    
    try:
        # Use copy() to bypass forward restrictions
        await message.copy(DESTINATION_CHANNEL)
        print("Message forwarded successfully!")
        
    except FloodWait as e:
        print(f"FloodWait detected. Waiting for {e.x} seconds.")
        await asyncio.sleep(e.x)
        await message.copy(DESTINATION_CHANNEL) # Retry after waiting
        print("Message forwarded successfully after waiting.")
        
    except Exception as e:
        print(f"An error occurred while forwarding: {e}")

# --- START THE CLIENT ---
async def main():
    print("Starting the forwarder bot...")
    await app.start()
    print("Bot is running and listening for new messages.")
    await asyncio.Event().wait() # Keep the script running

if __name__ == "__main__":
    # Create the 'data' directory if it doesn't exist
    if not os.path.exists('data'):
        os.makedirs('data')
        
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped.")
