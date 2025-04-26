import os
import time
import psutil
import tempfile
import getpass
import cv2
import sys
import logging
import subprocess
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Set up logging with console output
log_dir = os.path.join(os.path.expanduser("~"), "Services")
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    filename=os.path.join(log_dir, "RemoteDeactivation"),
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

# Load .env file
env_path = os.path.join(os.path.expanduser("~"), "Services", ".env.linux")
if not os.path.exists(env_path):
    print(f"ERROR: Environment file not found at {env_path}")
    sys.exit(1)

load_dotenv(env_path)

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_USER_ID_STR = os.getenv("ALLOWED_USER_ID")
DEVICE_NAME = os.getenv("DEVICE_NAME") or os.uname().nodename

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


def run_with_sudo(cmd_list):
    """Run command with sudo if needed, handling NOPASSWD sudo configuration"""
    try:
        # First try directly with sudo - works if NOPASSWD is configured
        return subprocess.run(cmd_list, check=True)
    except subprocess.CalledProcessError:
        logging.warning(f"Failed to run command with sudo: {cmd_list}")
        # Try without sudo as fallback
        try:
            return subprocess.run(cmd_list[1:], check=True)
        except subprocess.CalledProcessError as e:
            logging.error(f"Command failed without sudo: {e}")
            raise


async def shutdown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_command("shutdown", update.effective_user, context.args)
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized user.")
        return
    await update.message.reply_text(f"{DEVICE_NAME}: Shutting down now... 🧨💤")
    try:
        # Try systemctl first (modern Linux systems)
        run_with_sudo(['sudo', 'systemctl', 'poweroff'])
    except Exception as e:
        logging.warning(f"systemctl poweroff failed: {e}")
        try:
            # Fall back to traditional shutdown command
            run_with_sudo(['sudo', 'shutdown', '-h', 'now'])
        except Exception as e:
            logging.error(f"Shutdown failed: {e}")
            await update.message.reply_text(f"❌ Shutdown failed: {str(e)}")


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
    
    try:
        # For systemd-based systems
        if seconds < 60:
            # For very short times, use a sleep and immediate shutdown
            cmd = f'sleep {seconds} && sudo systemctl poweroff'
            subprocess.Popen(cmd, shell=True)
        else:
            # Convert to minutes for shutdown command (rounded up)
            minutes = (seconds + 59) // 60  # Round up to nearest minute
            run_with_sudo(['sudo', 'shutdown', '-h', f'+{minutes}'])
    except Exception as e:
        logging.error(f"Scheduled shutdown failed: {e}")
        await update.message.reply_text(f"❌ Scheduled shutdown failed: {str(e)}")


async def cancel_shutdown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_command("cancel_shutdown", update.effective_user, context.args)
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized user.")
        return
    
    try:
        run_with_sudo(['sudo', 'shutdown', '-c'])
        await update.message.reply_text(f"{DEVICE_NAME}: ✅ Shutdown canceled.")
    except Exception as e:
        logging.error(f"Cancel shutdown failed: {e}")
        await update.message.reply_text(f"❌ Cancel shutdown failed: {str(e)}")


async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_command("restart", update.effective_user, context.args)
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized user.")
        return
    
    await update.message.reply_text(f"{DEVICE_NAME}: Restarting now... 🔁💻")
    try:
        # Try systemctl first (modern Linux systems)
        run_with_sudo(['sudo', 'systemctl', 'reboot'])
    except Exception:
        try:
            # Fall back to traditional reboot command
            run_with_sudo(['sudo', 'reboot'])
        except Exception as e:
            logging.error(f"Restart failed: {e}")
            await update.message.reply_text(f"❌ Restart failed: {str(e)}")


async def lock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_command("lock", update.effective_user, context.args)
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized user.")
        return
    
    await update.message.reply_text(f"{DEVICE_NAME}: Locking now... 🔒")
    
    # Try different locking methods
    lock_methods = [
        # Detect running display server 
        lambda: os.environ.get('DISPLAY') and subprocess.call(['xdg-screensaver', 'lock']) == 0,
        # GNOME
        lambda: subprocess.call(['gnome-screensaver-command', '-l']) == 0,
        # GNOME newer versions
        lambda: subprocess.call(['dbus-send', '--type=method_call', '--dest=org.gnome.ScreenSaver', 
                               '/org/gnome/ScreenSaver', 'org.gnome.ScreenSaver.Lock']) == 0,
        # KDE
        lambda: subprocess.call(['qdbus', 'org.freedesktop.ScreenSaver', '/ScreenSaver', 'Lock']) == 0,
        # XFCE
        lambda: subprocess.call(['xflock4']) == 0,
        # i3/sway
        lambda: subprocess.call(['loginctl', 'lock-session']) == 0,
        # Light locker
        lambda: subprocess.call(['light-locker-command', '-l']) == 0,
        # XScreenSaver
        lambda: subprocess.call(['xscreensaver-command', '-lock']) == 0,
    ]
    
    success = False
    for method in lock_methods:
        try:
            if method():
                success = True
                break
        except (subprocess.SubprocessError, FileNotFoundError):
            continue
    
    if not success:
        logging.warning("All lock methods failed")
        await update.message.reply_text("⚠️ Lock attempted but may have failed")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_command("status", update.effective_user)
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized user.")
        return
    uptime_seconds = time.time() - psutil.boot_time()
    uptime_str = time.strftime("%H:%M:%S", time.gmtime(uptime_seconds))
    
    # Battery info - Linux specific approach
    battery_percent = "N/A"
    power_status = "N/A"
    try:
        battery = psutil.sensors_battery()
        if battery:
            battery_percent = f"{battery.percent}%"
            power_status = "⚡ Charging" if battery.power_plugged else "🔋 Not charging"
    except:
        # Fall back to reading from system files if psutil approach fails
        try:
            if os.path.exists("/sys/class/power_supply/BAT0/"):
                with open("/sys/class/power_supply/BAT0/capacity", "r") as f:
                    battery_percent = f"{f.read().strip()}%"
                with open("/sys/class/power_supply/BAT0/status", "r") as f:
                    status = f.read().strip()
                    power_status = "⚡ Charging" if status == "Charging" else "🔋 Not charging"
        except:
            pass
            
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
        tmp_filepath = os.path.join(tempfile.gettempdir(), "screenshot.png")
        
        # Linux screenshot using scrot
        try:
            subprocess.call(['scrot', tmp_filepath])
        except:
            # Fallback to import if scrot is not available
            try:
                subprocess.call(['import', '-window', 'root', tmp_filepath])
            except:
                # Another fallback using gnome-screenshot
                subprocess.call(['gnome-screenshot', '-f', tmp_filepath])

        if os.path.exists(tmp_filepath):
            with open(tmp_filepath, "rb") as photo:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id, photo=photo
                )
            logging.info("Screenshot sent successfully")
        else:
            raise Exception("Failed to create screenshot file")
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
        # Linux speech - try several TTS options
        tts_success = False
        
        # Try espeak
        try:
            subprocess.call(['espeak', message])
            tts_success = True
        except:
            pass
            
        # Try festival
        if not tts_success:
            try:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.txt') as f:
                    f.write(message)
                    f.flush()
                    subprocess.call(['festival', '--tts', f.name])
                    tts_success = True
            except:
                pass
                
        # Try pico2wave
        if not tts_success:
            try:
                with tempfile.NamedTemporaryFile(suffix='.wav') as f:
                    subprocess.call(['pico2wave', '-w', f.name, message])
                    subprocess.call(['aplay', f.name])
                    tts_success = True
            except:
                pass

        await update.message.reply_text(f"{DEVICE_NAME}: 📢 {message}")
        
        if not tts_success:
            logging.warning("Could not find a working TTS engine")
            
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
        print(f"✅ {DEVICE_NAME} Bot is running...")
        app.run_polling()
    except Exception as e:
        logging.error(f"Failed to start bot: {e}")
        sys.exit(1)