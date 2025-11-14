# /start, /votes, and the automatic updates,
import asyncio
import time
import subprocess
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, PicklePersistence
import requests


BOT_TOKEN = os.environ.get("BOT_TOKEN", "8243897329:AAF8u9bfRXbnm3ycWXFRQk-bwpBOjS8xFuQ")
API_URL = "https://fight.cryptofightclub.wtf/api/votes"
FIGHTER_NAMES = {'1': '$POPDOG', '2': '$LFGO'}

# (from i.imgur.com )
WELCOME_IMAGE_URL = "https://i.imgur.com/q2ofFCQ.jpeg"  # For the /start command
VOTES_COMMAND_IMAGE_URL = "https://i.imgur.com/281bIod.jpeg" # For the on-demand /votes command
AUTO_UPDATE_IMAGE_URL = "https://i.imgur.com/281bIod.jpeg" # For the repeating messages

AUTO_UPDATE_INTERVAL = 900
RUN_DURATION_HOURS = 48

# --- 2. CORE LOGIC & HELPERS ---
def get_vote_caption( ):
    try:
        response = requests.get(API_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and 'votes' in data and '1' in data['votes'] and '2' in data['votes']:
            vote_counts = data['votes']
            caption = (f"🥊 *Crypto Fight Club - Live Vote* 🥊\n\n"
                       f"*{FIGHTER_NAMES['1']}*: {vote_counts['1']} votes\n"
                       f"*{FIGHTER_NAMES['2']}*: {vote_counts['2']} votes\n\n"
                       f"_Last Update: {time.strftime('%H:%M:%S %Z')}_")
            return caption
        else: return "Error: Could not parse score data."
    except Exception as e: return f"Error: Could not connect to API. ({e})"

async def is_user_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if update.effective_chat.type == 'private': return True
    admins = await context.bot.get_chat_administrators(update.effective_chat.id)
    return update.effective_user.id in [admin.user.id for admin in admins]

def download_image_with_curl(url: str, output_path: str) -> bool:
    """Uses 'curl' to download an image and verifies it's not empty."""
    try:
        command = ["curl", "-L", "-o", output_path, "-s", url]
        subprocess.run(command, check=True, timeout=15)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            print(f"CURL download of '{url}' successful. Size: {os.path.getsize(output_path)} bytes.")
            return True
        else:
            print(f"CURL download failed: The file '{output_path}' is empty or missing.")
            return False
    except Exception as e:
        print(f"CURL download failed with an exception: {e}")
        return False

# --- 3. TELEGRAM COMMAND HANDLERS (Using their own image variables) ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for the /start command. Downloads and sends the WELCOME image."""
    welcome_caption = (
        "Hello! I am the Crypto Fight Club vote bot.\n\n"
        "Add me to your group and an admin can type /activate to start automatic updates. "
        "Anyone can use /votes to get the latest scores on-demand."
    )
    
    image_path = "./welcome_image.jpg"
    if download_image_with_curl(WELCOME_IMAGE_URL, image_path):
        with open(image_path, 'rb') as photo_file:
            await update.message.reply_photo(photo=photo_file, caption=welcome_caption)
    else:
        await update.message.reply_text("Sorry, the welcome image could not be loaded. " + welcome_caption)

async def votes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for the /votes command. Downloads and sends the VOTES_COMMAND image."""
    final_caption = get_vote_caption()
    
    image_path = "./votes_command_image.jpg"
    if download_image_with_curl(VOTES_COMMAND_IMAGE_URL, image_path):
        with open(image_path, 'rb') as photo_file:
            await update.message.reply_photo(photo=photo_file, caption=final_caption, parse_mode='Markdown')
    else:
        await update.message.reply_text("Sorry, the score image could not be loaded. Here is the data:\n\n" + final_caption, parse_mode='Markdown')

async def activate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_admin(update, context):
        await update.message.reply_text("Only group admins can use this command.")
        return
    chat_id = update.effective_chat.id
    if 'active_chats' not in context.bot_data: context.bot_data['active_chats'] = set()
    if chat_id in context.bot_data['active_chats']:
        await update.message.reply_text("Automatic updates are already active in this chat.")
    else:
        context.bot_data['active_chats'].add(chat_id)
        await update.message.reply_text("✅ Automatic updates have been activated!")
        print(f"Activated auto-updates for chat ID: {chat_id}")

async def deactivate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_admin(update, context):
        await update.message.reply_text("Only group admins can use this command.")
        return
    chat_id = update.effective_chat.id
    if 'active_chats' in context.bot_data and chat_id in context.bot_data['active_chats']:
        context.bot_data['active_chats'].remove(chat_id)
        await update.message.reply_text("❌ Automatic updates have been deactivated.")
        print(f"Deactivated auto-updates for chat ID: {chat_id}")
    else:
        await update.message.reply_text("Automatic updates were not active in this chat.")

# --- 4. AUTOMATIC UPDATE JOB (Using its own image variable) ---
async def auto_update_job(context: ContextTypes.DEFAULT_TYPE):
    print("\n--- Running public 'CURL Fallback' photo cycle ---")
    if not context.bot_data.get('active_chats'):
        print("No active chats. Skipping cycle.")
        return

    new_caption = get_vote_caption()
    if "Error" in new_caption:
        print(f"Failed to fetch new data, skipping update cycle. Reason: {new_caption}")
        return

    image_path = "./auto_update_image.jpg"
    if not download_image_with_curl(AUTO_UPDATE_IMAGE_URL, image_path):
        print("❌ Cycle stopped: Image download failed the validation check.")
        return

    for chat_id in list(context.bot_data['active_chats']):
        if context.bot_data.get(chat_id, {}).get('last_message_id'):
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=context.bot_data[chat_id]['last_message_id'])
            except Exception: pass
        try:
            with open(image_path, 'rb') as photo_file:
                new_message = await context.bot.send_photo(chat_id=chat_id, photo=photo_file, caption=new_caption, parse_mode='Markdown')
            if chat_id not in context.bot_data: context.bot_data[chat_id] = {}
            context.bot_data[chat_id]['last_message_id'] = new_message.message_id
            print(f"Sent new photo update to chat {chat_id}.")
        except Exception as e:
            print(f"❌ FAILED to send message to chat {chat_id}. Error: {e}")

# --- 5. MAIN BOT SETUP & RUN ---
async def main():
    print("Starting Ultimate Bot...")
    # Updated check for both an empty token and the placeholder text
    if not BOT_TOKEN or "PASTE YOUR BOT TOKEN HERE" in BOT_TOKEN:
        print("🛑 FATAL ERROR: Please fill in your BOT_TOKEN in the script or set it as a Secret.")
        return

    persistence = PicklePersistence(filepath="./bot_database.pkl")
    application = Application.builder().token(BOT_TOKEN).persistence(persistence).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("votes", votes_command))
    application.add_handler(CommandHandler("activate", activate_command))
    application.add_handler(CommandHandler("deactivate", deactivate_command))
    job_queue = application.job_queue
    job_queue.run_repeating(auto_update_job, interval=AUTO_UPDATE_INTERVAL, first=10)

    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    print(f"Bot started successfully. Listening for commands...")

    if RUN_DURATION_HOURS is not None:
        run_duration_seconds = RUN_DURATION_HOURS * 3600
        print(f"This bot will automatically shut down in {RUN_DURATION_HOURS} hours.")
        await asyncio.sleep(run_duration_seconds)
        print(f"\nShutting down bot after {RUN_DURATION_HOURS} hours.")
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
    else:
        print("This bot is set to run forever. Press Ctrl+C to stop.")
        while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot manually stopped by user.")
