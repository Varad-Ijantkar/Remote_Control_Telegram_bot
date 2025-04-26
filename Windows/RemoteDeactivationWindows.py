import os
import time
import psutil
import pyautogui
import tempfile
import getpass
import pyttsx3
import cv2
import sys
import logging
import ctypes
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Set up logging with console output
logging.basicConfig(
    filename=os.path.join(
        os.path.expanduser("~"), "daemon", "Windows", "RemoteDeactivation.log"
    ),
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    force=True,
)

# Add console handler for immediate feedback
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
console_handler.setFormatter(console_formatter)
logging.getLogger().addHandler(console_handler)

print("Logger initialized.")

# Reduce initial delay for testing
print("Waiting for network...")
time.sleep(5)  # Reduced from 30 for testing

# Load .env file - Adjust path to be more generic
env_path = os.path.join(os.path.expanduser("~"), "daemon", "Windows", ".env.w11")
if not os.path.exists(env_path):
    print(f"ERROR: Environment file not found at {env_path}")
    sys.exit(1)

load_dotenv(env_path)

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_USER_ID_STR = os.getenv("ALLOWED_USER_ID")
DEVICE_NAME = os.getenv("DEVICE_NAME") or os.environ.get("COMPUTERNAME", "Unknown")

try:
    ALLOWED_USER_ID = int(ALLOWED_USER_ID_STR) if ALLOWED_USER_ID_STR else None
except ValueError:
    print(f"ERROR: ALLOWED_USER_ID is not a valid integer: {ALLOWED_USER_ID_STR}")
    sys.exit(1)

# Validate environment variables
if not BOT_TOKEN:
    print("ERROR: BOT_TOKEN environment variable is missing or empty")
    logging.error("Missing BOT_TOKEN environment variable")
    sys.exit(1)

if not ALLOWED_USER_ID:
    print("ERROR: ALLOWED_USER_ID environment variable is missing or invalid")
    logging.error("Missing or invalid ALLOWED_USER_ID environment variable")
    sys.exit(1)


def is_authorized(user_id):
    return user_id == ALLOWED_USER_ID


def log_command(command, user, args=""):
    msg = f"🔹 {user.first_name} ({user.id}) used /{command} {args}".strip()
    logging.info(msg)


async def shutdown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_command("shutdown", update.effective_user, context.args)
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized user.")
        return
    await update.message.reply_text(f"{DEVICE_NAME}: Shutting down now... 🧨💤")
    os.system("shutdown /s /t 1")


async def shutdown_in_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_command("shutdown_in", update.effective_user, context.args)
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized user.")
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /shutdown_in [seconds]")
        return
    seconds = int(context.args[0])
    await update.message.reply_text(
        f"{DEVICE_NAME}: Scheduled shutdown in {seconds} seconds... ⏳"
    )
    os.system(f"shutdown /s /t {seconds}")


async def cancel_shutdown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_command("cancel_shutdown", update.effective_user, context.args)
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized user.")
        return
    os.system("shutdown /a")
    await update.message.reply_text(f"{DEVICE_NAME}: ✅ Shutdown canceled.")


async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_command("restart", update.effective_user, context.args)
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized user.")
        return
    await update.message.reply_text(f"{DEVICE_NAME}: Restarting now... 🔁💻")
    os.system("shutdown /r /t 1")


async def lock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_command("lock", update.effective_user, context.args)
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized user.")
        return
    try:
        await update.message.reply_text(f"{DEVICE_NAME}: Locking now... 🔒")
        # Windows-specific lock command
        ctypes.windll.user32.LockWorkStation()
    except Exception as e:
        logging.error(f"Lock command failed: {e}")
        await update.message.reply_text(f"❌ Lock failed: {str(e)}")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_command("status", update.effective_user)
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized user.")
        return
    uptime_seconds = time.time() - psutil.boot_time()
    uptime_str = time.strftime("%H:%M:%S", time.gmtime(uptime_seconds))
    battery = psutil.sensors_battery()
    battery_percent = f"{battery.percent}%" if battery else "N/A"
    power_status = (
        "⚡ Charging" if battery and battery.power_plugged else "🔋 Not charging"
    )
    msg = (
        f"💻 Status for {DEVICE_NAME}:\n"
        f"• Uptime: {uptime_str}\n"
        f"• Battery: {battery_percent}\n"
        f"• Power: {power_status}"
    )
    await update.message.reply_text(msg)


async def screenshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_command("screenshot", update.effective_user, context.args)
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized user.")
        return
    try:
        logging.info("Taking screenshot...")
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_filepath = tmp.name

            # Fix for the screenshot - ensure pyautogui works properly
            pyautogui.FAILSAFE = False
            # Wait a moment before taking screenshot to ensure everything is ready
            time.sleep(0.5)
            screenshot = pyautogui.screenshot()
            screenshot.save(tmp_filepath)

            with open(tmp_filepath, "rb") as photo:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id, photo=photo
                )
        logging.info("Screenshot sent successfully")
    except Exception as e:
        logging.error(f"Screenshot failed: {e}")
        await update.message.reply_text(f"❌ Screenshot failed: {str(e)}")
    finally:
        if "tmp_filepath" in locals() and os.path.exists(tmp_filepath):
            os.remove(tmp_filepath)


async def whoami_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_command("whoami", update.effective_user, context.args)
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized user.")
        return
    username = getpass.getuser()
    await update.message.reply_text(f"👤 Username: {username} on {DEVICE_NAME}")


async def say_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_command("say", update.effective_user, context.args)
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized user.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /say [message]")
        return
    message = " ".join(context.args)
    try:
        # Windows-specific speech synthesis
        engine = pyttsx3.init()
        engine.setProperty("rate", 150)
        engine.setProperty("volume", 1.0)

        # Set the specific voice to use (optional, but helps prevent issues)
        voices = engine.getProperty("voices")
        if voices:
            engine.setProperty("voice", voices[0].id)  # Use the first available voice

        # Use runAndWait with block=True to ensure audio is played
        engine.say(message)
        engine.runAndWait()

        await update.message.reply_text(f"{DEVICE_NAME}: 📢 {message}")
    except Exception as e:
        logging.error(f"Speech failed: {e}")
        await update.message.reply_text(f"❌ Failed to speak: {str(e)}")


async def camera_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_command("camera", update.effective_user, context.args)
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized user.")
        return
    try:
        await update.message.reply_text(f"{DEVICE_NAME}: Capturing image...")
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            raise Exception("Failed to open camera")

        # Try to set camera properties for better quality
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        ret, frame = cap.read()
        cap.release()

        if not ret:
            raise Exception("Failed to capture image from camera")

        # Convert from BGR to RGB to fix the green tint issue
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        filepath = os.path.join(tempfile.gettempdir(), "camera_image.png")

        # Save using OpenCV's imwrite with RGB conversion
        cv2.imwrite(filepath, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))

        with open(filepath, "rb") as photo:
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=photo)

    except Exception as e:
        logging.error(f"Camera command failed: {e}")
        await update.message.reply_text(f"❌ Failed to capture image: {str(e)}")
    finally:
        if "filepath" in locals() and os.path.exists(filepath):
            os.remove(filepath)


async def shutdown_bot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global app
    log_command("shutdown_bot", update.effective_user)
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized user.")
        return
    await update.message.reply_text(f"{DEVICE_NAME}: 🛑 Shutting down bot...")
    await app.stop()
    sys.exit()


if __name__ == "__main__":
    try:
        print("Building Telegram bot application...")
        app = ApplicationBuilder().token(BOT_TOKEN).build()

        print("Registering command handlers...")
        app.add_handler(CommandHandler("shutdown", shutdown_command))
        app.add_handler(CommandHandler("shutdown_in", shutdown_in_command))
        app.add_handler(CommandHandler("cancel_shutdown", cancel_shutdown_command))
        app.add_handler(CommandHandler("restart", restart_command))
        app.add_handler(CommandHandler("lock", lock_command))
        app.add_handler(CommandHandler("status", status_command))
        app.add_handler(CommandHandler("screenshot", screenshot_command))
        app.add_handler(CommandHandler("whoami", whoami_command))
        app.add_handler(CommandHandler("say", say_command))
        app.add_handler(CommandHandler("camera", camera_command))
        app.add_handler(CommandHandler("shutdown_bot", shutdown_bot_command))

        print(f"✅ {DEVICE_NAME} Bot is starting up...")
        logging.info(f"✅ {DEVICE_NAME} Bot is running...")

        print("Starting polling - bot is now online! Press Ctrl+C to stop.")
        app.run_polling()
    except Exception as e:
        error_msg = f"Failed to start bot: {e}"
        print(f"ERROR: {error_msg}")
        logging.error(error_msg)
        import traceback

        print(traceback.format_exc())
        sys.exit(1)
