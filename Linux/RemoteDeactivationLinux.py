#!/usr/bin/env python3
import os
import time
import psutil
import tempfile
import getpass
import cv2
import sys
import logging
import subprocess
import signal
import atexit
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Set up logging with console output
log_dir = os.path.join(os.path.expanduser("~"), "Services")
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    filename=os.path.join(log_dir, "RemoteDeactivation.log"),
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

# Load .env file
env_path = os.path.join(os.path.expanduser("~"), "Services", ".env.linux")
if not os.path.exists(env_path):
    print(f"ERROR: Environment file not found at {env_path}")
    logging.critical(f"Environment file not found at {env_path}")
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
    logging.critical(f"ALLOWED_USER_ID is not a valid integer: {ALLOWED_USER_ID_STR}")
    sys.exit(1)

# Validate environment variables
if not BOT_TOKEN:
    print("ERROR: BOT_TOKEN environment variable is missing or empty")
    logging.critical("Missing BOT_TOKEN environment variable")
    sys.exit(1)

if not ALLOWED_USER_ID:
    print("ERROR: ALLOWED_USER_ID environment variable is missing or invalid")
    logging.critical("Missing or invalid ALLOWED_USER_ID environment variable")
    sys.exit(1)

# Create a PID file to prevent multiple instances
pid_file = os.path.join(log_dir, "remote_deactivation.pid")

def is_process_running(pid):
    """Check if a process with the given PID is running"""
    try:
        os.kill(pid, 0) # Signal 0 does not kill but checks if process exists
        return True
    except OSError:
        return False

def check_single_instance():
    """Ensure only one instance of the bot is running"""
    if os.path.exists(pid_file):
        try:
            with open(pid_file, 'r') as f:
                old_pid = int(f.read().strip())
            if is_process_running(old_pid):
                # Check if the process is actually this script
                try:
                    old_proc = psutil.Process(old_pid)
                    # This check is a bit basic, could be more robust by checking script path
                    if "python" in old_proc.name() and any("RemoteDeactivation.py" in cmd_part for cmd_part in old_proc.cmdline()): # Assuming your script is named RemoteDeactivation.py
                        print(f"Another instance of this script is already running (PID: {old_pid})")
                        logging.info(f"Another instance of this script is already running (PID: {old_pid})")
                        sys.exit(1)
                    else:
                        print(f"PID {old_pid} is running but it's not this script. Stale PID file?")
                        logging.warning(f"PID {old_pid} is running but it's not this script. Stale PID file?")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    print(f"Found stale PID file. Previous instance (PID: {old_pid}) is not running or inaccessible.")
                    logging.info(f"Found stale PID file. Previous instance (PID: {old_pid}) is not running or inaccessible.")
            else:
                print(f"Found stale PID file. Previous instance (PID: {old_pid}) is not running.")
                logging.info(f"Found stale PID file. Previous instance (PID: {old_pid}) is not running.")
        except ValueError:
            print("Invalid PID in PID file. Removing stale file.")
            logging.warning("Invalid PID in PID file. Removing stale file.")
        except Exception as e:
            print(f"Error checking old PID: {e}. Assuming stale PID file.")
            logging.error(f"Error checking old PID: {e}. Assuming stale PID file.")
    
    # Write current PID to file
    with open(pid_file, 'w') as f:
        f.write(str(os.getpid()))

def cleanup():
    """Remove PID file on exit"""
    try:
        if os.path.exists(pid_file):
            with open(pid_file, 'r') as f:
                pid_in_file = int(f.read().strip())
            if pid_in_file == os.getpid(): # Only remove if it's our PID
                os.remove(pid_file)
                logging.info("Bot shutdown complete. PID file removed.")
            else:
                logging.info(f"Bot shutdown. PID file ({pid_file}) belongs to another PID ({pid_in_file}), not removing.")
        else:
            logging.info("Bot shutdown complete. PID file was already removed or not created.")
    except Exception as e:
        logging.error(f"Error during cleanup: {e}")


# Register cleanup function
atexit.register(cleanup)

# Handle termination signals
def signal_handler(sig, frame):
    print(f"Received signal {sig}. Cleaning up and exiting...")
    logging.info(f"Received signal {sig}. Cleaning up and exiting...")
    # cleanup() # atexit will call this
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def is_authorized(user_id):
    return user_id == ALLOWED_USER_ID

def log_command(command, user, args=""):
    args_str = " ".join(map(str, args)) if isinstance(args, list) else str(args)
    msg = f"🔹 {user.first_name} ({user.id}) used /{command} {args_str}".strip()
    logging.info(msg)

def run_command(cmd_list, use_shell=False, env=None):
    """Run command, returns (success, output_stdout, output_stderr)"""
    try:
        process_env = os.environ.copy()
        if env:
            process_env.update(env)
            
        if use_shell:
            # Ensure cmd_list is a string if use_shell is True
            cmd_to_run = cmd_list if isinstance(cmd_list, str) else subprocess.list2cmdline(cmd_list)
            result = subprocess.run(cmd_to_run, shell=True, check=True, capture_output=True, text=True, env=process_env)
        else:
            result = subprocess.run(cmd_list, check=True, capture_output=True, text=True, env=process_env)
        return True, result.stdout.strip(), result.stderr.strip()
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed: {cmd_list}. Return code: {e.returncode}. Stdout: {e.stdout.strip()}. Stderr: {e.stderr.strip()}")
        return False, e.stdout.strip(), e.stderr.strip()
    except FileNotFoundError:
        logging.error(f"Command not found: {cmd_list[0] if isinstance(cmd_list, list) else cmd_list.split()[0]}")
        return False, "", f"Command not found: {cmd_list[0] if isinstance(cmd_list, list) else cmd_list.split()[0]}"


def check_command_exists(command):
    """Check if a command is available on the system"""
    # Use `shutil.which` for a more robust check than `subprocess.run(['which', ...])`
    # return subprocess.run(['which', command], capture_output=True, text=True).returncode == 0
    import shutil
    return shutil.which(command) is not None

def get_wayland_env():
    """Set up environment variables for Wayland/Hyprland.
    Ensure this script runs in an environment that has access to the WayLAND_DISPLAY
    compositor, which usually means being a child process of the user's graphical session or having
    critical environment variables correctly set and accessible.
    For systemd user services, consider `systemctl --user import-environment` for these variables
    or passing them via PassEnvironment/Environment in the service file.
    Key variables: DISPLAY, WAYLAND_DISPLAY, XDG_RUNTIME_DIR, DBUS_SESSION_BUS_ADDRESS, HYPRLAND_INSTANCE_SIGNATURE
    """
    env = os.environ.copy() # Start with a copy of the current environment
    log_messages = ["Attempting to establish Wayland/X11 environment for subprocesses:"]

    # XDG_RUNTIME_DIR
    if 'XDG_RUNTIME_DIR' not in env:
        uid = os.getuid()
        env['XDG_RUNTIME_DIR'] = f'/run/user/{uid}'
        log_messages.append(f"  - XDG_RUNTIME_DIR: Not set, defaulted to {env['XDG_RUNTIME_DIR']}")
    else:
        log_messages.append(f"  - XDG_RUNTIME_DIR: Using existing value: {env['XDG_RUNTIME_DIR']}")

    # WAYLAND_DISPLAY
    if 'WAYLAND_DISPLAY' not in env:
        xdg_runtime_dir = env.get('XDG_RUNTIME_DIR')
        if xdg_runtime_dir and os.path.exists(xdg_runtime_dir):
            try:
                potential_wl_displays = [
                    f for f in os.listdir(xdg_runtime_dir) 
                    if f.startswith('wayland-') and 
                       (os.path.islink(os.path.join(xdg_runtime_dir, f)) or 
                        # Check if it's a socket (more reliable)
                        os.stat(os.path.join(xdg_runtime_dir, f)).st_mode & 0o170000 == 0o140000) # S_IFSOCK
                ]
                if potential_wl_displays:
                    env['WAYLAND_DISPLAY'] = sorted(potential_wl_displays)[0]
                    log_messages.append(f"  - WAYLAND_DISPLAY: Not set, detected and set to {env['WAYLAND_DISPLAY']} from XDG_RUNTIME_DIR")
                else:
                    env['WAYLAND_DISPLAY'] = 'wayland-0' # Last resort guess
                    log_messages.append(f"  - WAYLAND_DISPLAY: Not set, no obvious socket in XDG_RUNTIME_DIR, defaulting to {env['WAYLAND_DISPLAY']}")
            except Exception as e:
                env['WAYLAND_DISPLAY'] = 'wayland-0' # Fallback on error listing dir
                log_messages.append(f"  - WAYLAND_DISPLAY: Error detecting from XDG_RUNTIME_DIR ({e}), defaulting to {env['WAYLAND_DISPLAY']}")
        else:
            env['WAYLAND_DISPLAY'] = 'wayland-0' # Last resort guess
            log_messages.append(f"  - WAYLAND_DISPLAY: Not set, XDG_RUNTIME_DIR also not available or invalid, defaulting to {env['WAYLAND_DISPLAY']}")
    else:
        log_messages.append(f"  - WAYLAND_DISPLAY: Using existing value: {env['WAYLAND_DISPLAY']}")

    # DISPLAY (for XWayland/X11)
    if 'DISPLAY' not in env:
        env['DISPLAY'] = ':0'
        log_messages.append(f"  - DISPLAY: Not set, defaulting to {env['DISPLAY']}")
    else:
        log_messages.append(f"  - DISPLAY: Using existing value: {env['DISPLAY']}")

    # DBUS_SESSION_BUS_ADDRESS
    if 'DBUS_SESSION_BUS_ADDRESS' not in env:
        if 'XDG_RUNTIME_DIR' in env and os.path.exists(env['XDG_RUNTIME_DIR']):
            bus_path = os.path.join(env['XDG_RUNTIME_DIR'], 'bus')
            # Check if the bus socket actually exists
            if os.path.exists(bus_path) and (os.stat(bus_path).st_mode & 0o170000 == 0o140000): # S_IFSOCK
                env['DBUS_SESSION_BUS_ADDRESS'] = f"unix:path={bus_path}"
                log_messages.append(f"  - DBUS_SESSION_BUS_ADDRESS: Not set, defaulted to {env['DBUS_SESSION_BUS_ADDRESS']}")
            else:
                log_messages.append(f"  - DBUS_SESSION_BUS_ADDRESS: Not set, and default path {bus_path} does not exist or is not a socket. GUI/session tools might fail.")
        else:
            log_messages.append("  - DBUS_SESSION_BUS_ADDRESS: Not set, and XDG_RUNTIME_DIR is unavailable to guess. GUI/session tools might fail.")
    else:
        log_messages.append(f"  - DBUS_SESSION_BUS_ADDRESS: Using existing value: {env['DBUS_SESSION_BUS_ADDRESS']}")

    # HYPRLAND_INSTANCE_SIGNATURE
    if 'HYPRLAND_INSTANCE_SIGNATURE' not in env:
        log_messages.append("  - HYPRLAND_INSTANCE_SIGNATURE: Not set in environment. Hyprland-specific tools (e.g., grimblast via hyprctl) may fail.")
    else:
        log_messages.append(f"  - HYPRLAND_INSTANCE_SIGNATURE: Using existing value: {env['HYPRLAND_INSTANCE_SIGNATURE']}")
    
    logging.info("\n".join(log_messages))
    return env

    """Set up environment variables for Wayland/Hyprland.
    Ensure this script runs in an environment that has access to the Wayland compositor,
    which usually means being a child process of the user's graphical session or having
    XDG_RUNTIME_DIR, WAYLAND_DISPLAY, and DBUS_SESSION_BUS_ADDRESS correctly set and accessible.
    For systemd user services, consider `systemctl --user import-environment` for these variables.
    """
    env = os.environ.copy()
    # Prefer existing environment variables if they are already set
    if 'WAYLAND_DISPLAY' not in env:
        env['WAYLAND_DISPLAY'] = 'wayland-0' # Default, but might not always be correct
    if 'XDG_RUNTIME_DIR' not in env:
        env['XDG_RUNTIME_DIR'] = f'/run/user/{os.getuid()}'
    if 'DISPLAY' not in env: # For XWayland fallback
        env['DISPLAY'] = ':0'
    # DBUS_SESSION_BUS_ADDRESS is also critical for many desktop interactions
    if 'DBUS_SESSION_BUS_ADDRESS' not in env and 'XDG_RUNTIME_DIR' in env:
         # Common path, but can vary. Best if inherited.
        env['DBUS_SESSION_BUS_ADDRESS'] = f"unix:path={env['XDG_RUNTIME_DIR']}/bus"
    return env

async def shutdown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_command("shutdown", update.effective_user, context.args)
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized user.")
        return
    
    await update.message.reply_text(f"{DEVICE_NAME}: Attempting to shut down now... 🧨💤")
    logging.info("Attempting shutdown...")
    
    # Try several methods to shutdown without requiring sudo
    # Note: Failures often mean permission issues (polkit rules needed for the user running the bot)
    # or issues with the loginctl/systemd setup on the specific machine.
    methods = [
        (["loginctl", "poweroff"], "loginctl direct"), # Standard systemd command
        (["systemctl", "poweroff"], "systemctl direct"), # Usually requires root, but some polkit configs might allow
        (["dbus-send", "--system", "--print-reply", "--dest=org.freedesktop.login1", 
          "/org/freedesktop/login1", "org.freedesktop.login1.Manager.PowerOff", "boolean:false"], "D-Bus system"),
        # Fallback for older systems or if loginctl acts weirdly, though less common now
        # (systemctl poweroff --user failed in logs, so removed)
    ]
    
    method_failed = False
    for cmd, name in methods:
        logging.info(f"Trying shutdown method: {name} ({cmd})")
        success, _, stderr = run_command(cmd)
        if success:
            # If command runs but system doesn't shut down, it might still 'succeed' here.
            # True success is system actually powering off. This bot can't confirm that post-command.
            logging.info(f"Shutdown method {name} executed. Assuming shutdown initiated.")
            # No further message to user as system should be shutting down.
            return 
        else:
            logging.warning(f"Shutdown method {name} failed. Stderr: {stderr}")
            if "Unknown command verb" in stderr and "loginctl" in cmd[0]:
                 logging.error("`loginctl` reported 'Unknown command verb'. "
                               "This is unusual. Check `loginctl` installation, version, and try running "
                               "`loginctl poweroff` manually in terminal. Ensure $PATH is correct.")
            elif "Interactive authentication required" in stderr:
                 logging.error("D-Bus requires interactive authentication. "
                               "This is a permission issue. Configure Polkit for the user running this bot "
                               "to allow `org.freedesktop.login1.power-off`.")
            method_failed = True
            
    if method_failed: # Only send if at least one method was attempted and all failed
        err_msg = (f"❌ Shutdown failed on {DEVICE_NAME}. All attempted methods failed. "
                   "This usually indicates permission issues (Polkit rules for the bot's user may be required for 'loginctl' or D-Bus actions) "
                   "or problems with the system's power management tools.")
        await update.message.reply_text(err_msg)
        logging.error("All direct shutdown methods failed.")


async def shutdown_in_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_command("shutdown_in", update.effective_user, context.args)
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized user.")
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /shutdown_in [seconds]")
        return
    
    seconds = int(context.args[0])
    if seconds <= 0:
        await update.message.reply_text("Please provide a positive number of seconds.")
        return

    await update.message.reply_text(
        f"{DEVICE_NAME}: Scheduled shutdown in {seconds} seconds... ⏳"
    )
    
    # This command will also rely on `loginctl poweroff` permissions.
    # If direct shutdown fails, this likely will too when `loginctl poweroff` executes.
    # Consider using `shutdown +minutes` if root privileges were available, but sticking to loginctl for user-level.
    
    # Using full path to sleep can be more robust in some minimal environments
    sleep_path = shutil.which("sleep") or "sleep" 
    loginctl_path = shutil.which("loginctl") or "loginctl"

    # The command to be executed in the background
    # Using `nohup` and `&` along with `start_new_session=True` for robust detachment
    cmd_str = f"nohup {sleep_path} {seconds} && {loginctl_path} poweroff &"
    
    logging.info(f"Scheduling shutdown with command: {cmd_str}")
    try:
        # Using Popen for more control and to detach properly
        subprocess.Popen(cmd_str, shell=True, 
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                         start_new_session=True) # Key for detaching
        logging.info(f"Scheduled shutdown process initiated. System should power off in {seconds} seconds via '{loginctl_path} poweroff'.")
    except Exception as e:
        logging.error(f"Scheduled shutdown failed to start: {e}")
        await update.message.reply_text(f"❌ Scheduled shutdown failed to start: {str(e)}")


async def cancel_shutdown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_command("cancel_shutdown", update.effective_user, context.args)
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized user.")
        return
    
    # This will attempt to kill the `sleep` process that is waiting to trigger `loginctl poweroff`
    # It also tries to cancel systemd shutdown timers if any were set by `shutdown -c` compatible commands
    # (though current script doesn't use `shutdown -c`)
    
    killed_sleep = False
    try:
        # More specific pkill pattern
        # Look for sleep processes that are parents of a future loginctl poweroff
        # This is tricky with simple pkill. A more robust way would be to store PID of Popen.
        # For now, keep it simple:
        pkill_cmd = ['pkill', '-f', f"{shutil.which('sleep') or 'sleep'}.*{shutil.which('loginctl') or 'loginctl'} poweroff"]
        logging.info(f"Attempting to cancel shutdown with: {pkill_cmd}")
        result = subprocess.run(pkill_cmd, capture_output=True, text=True)
        
        if result.returncode == 0: # pkill returns 0 if one or more processes were killed
            killed_sleep = True
            logging.info("Found and killed a pending 'sleep && loginctl poweroff' command.")
        elif result.returncode == 1: # pkill returns 1 if no processes matched
            logging.info("No 'sleep && loginctl poweroff' processes found by pkill.")
        else: # Other errors
            logging.warning(f"pkill command returned {result.returncode}. Stderr: {result.stderr.strip()}")
            
    except FileNotFoundError:
        logging.error("`pkill` command not found. Cannot cancel shutdown by this method.")
        await update.message.reply_text(f"❌ `pkill` not found. Cannot cancel.")
        return
    except Exception as e:
        logging.error(f"Error trying to pkill scheduled shutdown: {e}")
        # Don't send message yet, try systemctl method if applicable

    # Additionally, try to cancel any system-wide shutdown (e.g., if `shutdown +m` was used somehow)
    # This might require root or specific polkit permissions.
    cancelled_system_shutdown = False
    if check_command_exists("shutdown"):
        success, _, stderr = run_command(["shutdown", "-c"])
        if success:
            cancelled_system_shutdown = True
            logging.info("Executed `shutdown -c` successfully.")
        elif "Interactive authentication required" in stderr or "must be root" in stderr.lower():
            logging.warning("`shutdown -c` requires higher privileges which are not available.")
        elif stderr: # Other errors from shutdown -c
             logging.warning(f"`shutdown -c` failed: {stderr}")


    if killed_sleep or cancelled_system_shutdown:
        await update.message.reply_text(f"{DEVICE_NAME}: ✅ Shutdown canceled.")
    else:
        await update.message.reply_text(f"{DEVICE_NAME}: ❓ No pending shutdown found or cancellation failed (check logs for details).")


async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_command("restart", update.effective_user, context.args)
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized user.")
        return
    await update.message.reply_text(f"{DEVICE_NAME}: Attempting to restart now... 🔁💻")
    logging.info("Attempting restart...")

    methods = [
        (["loginctl", "reboot"], "loginctl direct"),
        (["systemctl", "reboot"], "systemctl direct"),
        (["dbus-send", "--system", "--print-reply", "--dest=org.freedesktop.login1", 
          "/org/freedesktop/login1", "org.freedesktop.login1.Manager.Reboot", "boolean:false"], "D-Bus system"),
    ]
    
    method_failed = False
    for cmd, name in methods:
        logging.info(f"Trying restart method: {name} ({cmd})")
        success, _, stderr = run_command(cmd)
        if success:
            logging.info(f"Restart method {name} executed. Assuming restart initiated.")
            return
        else:
            logging.warning(f"Restart method {name} failed. Stderr: {stderr}")
            if "Unknown command verb" in stderr and "loginctl" in cmd[0]:
                 logging.error("`loginctl` reported 'Unknown command verb'. "
                               "Check `loginctl` installation/version and try `loginctl reboot` manually.")
            elif "Interactive authentication required" in stderr:
                 logging.error("D-Bus requires interactive authentication. Configure Polkit for `org.freedesktop.login1.reboot`.")
            method_failed = True

    if method_failed:
        err_msg = (f"❌ Restart failed on {DEVICE_NAME}. All attempted methods failed. "
                   "This usually indicates permission issues (Polkit rules may be required) "
                   "or problems with the system's power management tools.")
        await update.message.reply_text(err_msg)
        logging.error("All direct restart methods failed.")


async def lock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_command("lock", update.effective_user, context.args)
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized user.")
        return
    
    await update.message.reply_text(f"{DEVICE_NAME}: Attempting to lock screen now... 🔒")
    
    current_env = get_wayland_env()
    logging.info(f"Using environment for lock command: {current_env.get('WAYLAND_DISPLAY')}, {current_env.get('XDG_RUNTIME_DIR')}, Display: {current_env.get('DISPLAY')}")

    # Hyprland-specific tools first, then fallbacks
    # Order can be adjusted based on preference
    lock_methods = [
        (["hyprlock"], "hyprlock"),                             # Preferred for Hyprland if available
        (["swaylock"], "swaylock"),                             # Common Wayland locker
        (["hyprctl", "dispatch", "exec", "hyprlock"], "hyprctl exec hyprlock"), # Alternative for hyprlock
        (["loginctl", "lock-session"], "loginctl lock-session"), # Systemd session lock
        # Add other lockers if needed e.g. i3lock for X11, physlock for console
    ]
    
    success = False
    tried_tools_details = [] # To store (tool_name, found_status, execution_stderr)

    for cmd_list, tool_name in lock_methods:
        tool_found = check_command_exists(cmd_list[0])
        if not tool_found:
            logging.info(f"Lock tool '{tool_name}' ({cmd_list[0]}) not found.")
            tried_tools_details.append({'name': tool_name, 'found': False, 'status': 'not found', 'stderr': ''})
            continue
        
        logging.info(f"Attempting to lock with '{tool_name}' using command: {' '.join(cmd_list)}")
        # For lock commands, we often don't need to capture output, just success/failure.
        # Using subprocess.run directly for more control over env and potential non-zero success.
        try:
            # Some lockers might fork and return immediately. `check=True` assumes a non-zero return code is an error.
            # Timeout can be useful if a locker hangs
            proc = subprocess.run(cmd_list, env=current_env, check=True, capture_output=True, text=True, timeout=5)
            # If `check=True` is used, a CalledProcessError is raised on non-zero exit, so this part might only be reached on 0.
            # Some tools might return non-zero on success in specific daemonized modes. This needs tool-specific handling if so.
            logging.info(f"Lock method '{tool_name}' executed successfully. stdout: {proc.stdout.strip()}, stderr: {proc.stderr.strip()}")
            success = True
            tried_tools_details.append({'name': tool_name, 'found': True, 'status': 'succeeded', 'stderr': proc.stderr.strip()})
            break 
        except subprocess.CalledProcessError as e:
            logging.warning(f"Lock method '{tool_name}' failed with exit code {e.returncode}. Stderr: {e.stderr.strip()}")
            tried_tools_details.append({'name': tool_name, 'found': True, 'status': f'failed (code {e.returncode})', 'stderr': e.stderr.strip()})
        except subprocess.TimeoutExpired:
            logging.warning(f"Lock method '{tool_name}' timed out.")
            tried_tools_details.append({'name': tool_name, 'found': True, 'status': 'timed out', 'stderr': 'Timeout after 5 seconds'})
        except Exception as e: # Catch other errors like FileNotFoundError if check_command_exists was wrong, or permission issues
            logging.error(f"An unexpected error occurred while trying to run lock method '{tool_name}': {e}")
            tried_tools_details.append({'name': tool_name, 'found': True, 'status': f'error ({type(e).__name__})', 'stderr': str(e)})
            
    if success:
        await update.message.reply_text(f"{DEVICE_NAME}: ✅ Screen lock initiated.")
    else:
        error_messages = []
        found_but_failed_tools = []
        missing_tools_list = []

        for detail in tried_tools_details:
            if not detail['found']:
                missing_tools_list.append(detail['name'])
            elif detail['status'] != 'succeeded':
                found_but_failed_tools.append(f"{detail['name']} ({detail['status']}" + (f": {detail['stderr']}" if detail['stderr'] else "") + ")")
        
        if not any(d['found'] for d in tried_tools_details): # No configured tools were found
             final_error_msg = f"❌ Lock failed. None of the configured lock utilities found. Please install one of: {', '.join(lm[1] for lm in lock_methods)}."
        elif found_but_failed_tools: # Some tools were found but all of them failed
            final_error_msg = (f"❌ Lock failed. The following screen locking utilities were found but failed to execute correctly: "
                         f"{'; '.join(found_but_failed_tools)}. This could be due to issues with the tools, "
                         f"their configuration, or the script's execution environment (e.g., not having access to an active display session).")
            if missing_tools_list:
                final_error_msg += f" Additionally, these tools were not found: {', '.join(missing_tools_list)}."
        else: # Should not happen if success is False and some tools were found
            final_error_msg = "❌ Lock failed. An unknown error occurred. Check logs for details."

        logging.error(f"Final lock error summary: {final_error_msg} | Details: {tried_tools_details}")
        await update.message.reply_text(final_error_msg)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_command("status", update.effective_user)
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized user.")
        return
    
    # Get uptime
    try:
        boot_time_timestamp = psutil.boot_time()
        current_time_timestamp = time.time()
        uptime_seconds = current_time_timestamp - boot_time_timestamp
        
        days, remainder = divmod(uptime_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        uptime_str_parts = []
        if days > 0:
            uptime_str_parts.append(f"{int(days)}d")
        if hours > 0 or days > 0: # Show hours if days are shown or if hours > 0
            uptime_str_parts.append(f"{int(hours):02}h")
        uptime_str_parts.append(f"{int(minutes):02}m")
        uptime_str_parts.append(f"{int(seconds):02}s")
        uptime_str = " ".join(uptime_str_parts) if uptime_str_parts else "Just booted"

    except Exception as e:
        logging.error(f"Could not get uptime: {e}")
        uptime_str = "N/A"
    
    # Get battery info
    battery_percent = "N/A"
    power_status = "N/A"
    battery_time_remaining = ""

    try:
        battery = psutil.sensors_battery()
        if battery:
            battery_percent = f"{battery.percent:.0f}%" # No decimals for percent
            power_status = "⚡ Charging" if battery.power_plugged else "🔋 Discharging"
            if battery.power_plugged:
                if hasattr(battery, 'secsleft') and battery.secsleft != psutil.POWER_TIME_UNLIMITED and battery.secsleft > 0:
                     # secs left usually means time to full when charging, if supported
                     m, s = divmod(battery.secsleft, 60)
                     h, m = divmod(m, 60)
                     if h > 0 : battery_time_remaining = f" ({h}h {m}m to full)"
                     elif m > 0 : battery_time_remaining = f" ({m}m {s}s to full)"
            else: # Discharging
                if hasattr(battery, 'secsleft') and battery.secsleft != psutil.POWER_TIME_UNLIMITED and battery.secsleft > 0:
                    m, s = divmod(battery.secsleft, 60)
                    h, m = divmod(m, 60)
                    if h > 0 : battery_time_remaining = f" ({h}h {m}m left)"
                    elif m > 0 : battery_time_remaining = f" ({m}m {s}s left)"
        else: # psutil found no battery, try sysfs as fallback
            raise AttributeError("psutil.sensors_battery() returned None")
            
    except (AttributeError, NotImplementedError, Exception) as e_psutil:
        logging.info(f"psutil.sensors_battery() failed or not available: {e_psutil}. Trying sysfs.")
        battery_paths = [
            "/sys/class/power_supply/BAT0/",
            "/sys/class/power_supply/BAT1/",
            "/sys/class/power_supply/battery/" # Generic name
        ]
        
        for path in battery_paths:
            if os.path.exists(os.path.join(path, "capacity")) and os.path.exists(os.path.join(path, "status")):
                try:
                    with open(os.path.join(path, "capacity"), "r") as f:
                        bat_cap = f.read().strip()
                        battery_percent = f"{bat_cap}%"
                    with open(os.path.join(path, "status"), "r") as f:
                        status_val = f.read().strip().lower()
                        if status_val == "charging":
                            power_status = "⚡ Charging"
                        elif status_val == "discharging":
                            power_status = "🔋 Discharging"
                        elif status_val == "full":
                            power_status = "🔌 Fully Charged"
                        elif status_val == "not charging": # Some devices report this when full and plugged in
                            power_status = "🔌 Not Charging (Plugged In)"
                        else:
                            power_status = f"{status_val.capitalize()}"
                    # Sysfs time remaining is often in `charge_full` vs `charge_now` and `current_now`
                    # This is more complex than psutil, so skipping for now unless critical.
                    break 
                except Exception as e_sysfs:
                    logging.warning(f"Failed to read battery info from {path}: {e_sysfs}")
                    battery_percent = "N/A (sysfs err)"
                    power_status = "N/A (sysfs err)"
                    pass # Try next path
    
    # Get memory info
    try:
        memory = psutil.virtual_memory()
        memory_total_gb = memory.total / (1024**3)
        memory_used_gb = memory.used / (1024**3)
        memory_info = f"{memory_used_gb:.1f}GB / {memory_total_gb:.1f}GB ({memory.percent}%)"
    except Exception as e:
        logging.error(f"Could not get memory info: {e}")
        memory_info = "N/A"
    
    # Get CPU load (average over 1 second)
    try:
        cpu_percent = f"{psutil.cpu_percent(interval=1)}%"
    except Exception as e:
        logging.error(f"Could not get CPU percent: {e}")
        cpu_percent = "N/A"
        
    # Get CPU temperature (more platform-dependent)
    cpu_temp_str = "N/A"
    try:
        temps = psutil.sensors_temperatures()
        # Common keys: 'coretemp', 'k10temp', 'zenpower', 'acpitz'
        # Look for a common CPU temperature sensor. This might need adjustment per system.
        # Prioritize 'k10temp' or 'coretemp' for package temperature if available.
        relevant_temps = []
        if 'coretemp' in temps:
            for entry in temps['coretemp']:
                if entry.label == 'Package id 0' or not entry.label or 'CPU' in entry.label.upper(): # Package temp or generic CPU
                    relevant_temps.append(entry.current)
                    break # Take the first relevant one
        if not relevant_temps and 'k10temp' in temps: # AMD
             for entry in temps['k10temp']: # Often Tctl or Tccd1
                if 'Tctl' in entry.label or 'Tccd' in entry.label:
                    relevant_temps.append(entry.current)
                    break
        if not relevant_temps and 'cpu_thermal' in temps : # Some systems like RPi
            relevant_temps.append(temps['cpu_thermal'][0].current)

        if relevant_temps:
            cpu_temp_str = f"{max(relevant_temps):.1f}°C" # Show the highest relevant temp found
        elif temps: # If temps dict is not empty but no specific one found
            # Fallback: just grab first available temp that seems plausible for CPU
            for key in temps:
                if temps[key]:
                    cpu_temp_str = f"{temps[key][0].current:.1f}°C (sensor: {temps[key][0].label or key})"
                    break


    except (AttributeError, NotImplementedError, Exception) as e:
        logging.warning(f"Could not get CPU temperature via psutil: {e}. Platform specific.")
        # You could add platform-specific commands here as a fallback e.g. for Raspberry Pi:
        # if os.path.exists("/sys/class/thermal/thermal_zone0/temp"):
        # try:
        # with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
        # temp = int(f.read().strip()) / 1000.0
        # cpu_temp_str = f"{temp:.1f}°C (sysfs)"
        # except: pass


    msg = (
        f"💻 **Status for {DEVICE_NAME}**:\n\n"
        f"🕰️ **Uptime**: {uptime_str}\n"
        f"⚡ **CPU Load**: {cpu_percent}\n"
        f"🌡️ **CPU Temp**: {cpu_temp_str}\n"
        f"🧠 **Memory**: {memory_info}\n"
        f"🔋 **Battery**: {battery_percent}{battery_time_remaining}\n"
        f"🔌 **Power**: {power_status}"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')


async def screenshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_command("screenshot", update.effective_user, context.args)
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized user.")
        return
    
    await update.message.reply_text(f"{DEVICE_NAME}: Taking screenshot... 📸")
    
    tmp_filepath = os.path.join(tempfile.gettempdir(), f"screenshot_{DEVICE_NAME}_{int(time.time())}.png")
    current_env = get_wayland_env()
    logging.info(f"Using environment for screenshot: Wayland Display: {current_env.get('WAYLAND_DISPLAY')}, XDG Runtime Dir: {current_env.get('XDG_RUNTIME_DIR')}, Display: {current_env.get('DISPLAY')}")

    # List of screenshot methods to try, in order of preference.
    # Ensure these tools are installed and configured on the target system.
    # For Wayland, grim-based tools are common. `hyprshot` might be specific to Hyprland setups.
    screenshot_methods = []
    if check_command_exists("grimblast"):
        # grimblast has various modes: output, area, active, screen
        screenshot_methods.append((["grimblast", "save", "screen", tmp_filepath], "grimblast screen"))
    if check_command_exists("hyprshot"): # Hyprland specific, often flexible
        screenshot_methods.append((["hyprshot", "-m", "output", "-o", os.path.dirname(tmp_filepath), "-f", os.path.basename(tmp_filepath)], "hyprshot output"))
    if check_command_exists("grim"): # Basic Wayland screenshot tool
        screenshot_methods.append((["grim", tmp_filepath], "grim")) # Takes full screen by default
    # Add other tools like `scrot` for X11 if needed as fallbacks, checking $DISPLAY or $WAYLAND_DISPLAY
    
    if not screenshot_methods:
        errmsg = "❌ No suitable screenshot tools (grimblast, hyprshot, grim) found. Please install one."
        logging.error(errmsg)
        await update.message.reply_text(errmsg)
        return
            
    screenshot_taken = False
    for cmd_list, tool_name in screenshot_methods:
        logging.info(f"Attempting screenshot with '{tool_name}' using command: {' '.join(cmd_list)}")
        try:
            # Timeout is important as some tools might hang or require interaction
            proc = subprocess.run(cmd_list, env=current_env, check=True, capture_output=True, text=True, timeout=10)
            if os.path.exists(tmp_filepath) and os.path.getsize(tmp_filepath) > 0:
                screenshot_taken = True
                logging.info(f"Screenshot taken successfully with '{tool_name}'. Output: {proc.stdout.strip() if proc.stdout else 'No stdout'}")
                break
            else:
                # Command succeeded but file wasn't created or is empty
                logging.warning(f"Screenshot method '{tool_name}' ran but didn't create a valid file at '{tmp_filepath}'. Stdout: {proc.stdout.strip()}, Stderr: {proc.stderr.strip()}")
        except subprocess.CalledProcessError as e:
            logging.warning(f"Screenshot method '{tool_name}' failed with exit code {e.returncode}. Stderr: {e.stderr.strip()}. Stdout: {e.stdout.strip()}")
        except subprocess.TimeoutExpired:
            logging.warning(f"Screenshot method '{tool_name}' timed out.")
        except Exception as e:
            logging.error(f"An unexpected error occurred with screenshot tool '{tool_name}': {e}")
            
    if screenshot_taken and os.path.exists(tmp_filepath):
        try:
            with open(tmp_filepath, "rb") as photo_file:
                await context.bot.send_photo(chat_id=update.effective_chat.id, photo=photo_file, caption=f"Screenshot from {DEVICE_NAME} via {tool_name}")
            logging.info("Screenshot sent successfully.")
        except Exception as e:
            logging.error(f"Failed to send screenshot photo: {e}")
            await update.message.reply_text(f"❌ Failed to send screenshot: {str(e)}")
    else:
        error_msg = (f"❌ Failed to take screenshot on {DEVICE_NAME}. All attempted methods failed. "
                     "Ensure a Wayland screenshot tool (grimblast, hyprshot, grim) is installed and configured, "
                     "and that the bot is running in an environment with access to the display server.")
        logging.error(error_msg + f" Tried methods: {[m[1] for m in screenshot_methods]}")
        await update.message.reply_text(error_msg)
            
    if os.path.exists(tmp_filepath):
        try:
            os.remove(tmp_filepath)
        except OSError as e:
            logging.warning(f"Could not remove temporary screenshot file {tmp_filepath}: {e}")


async def whoami_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_command("whoami", update.effective_user, context.args)
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized user.")
        return
    
    try:
        username = getpass.getuser()
    except Exception as e:
        username = "N/A (Error getting username)"
        logging.error(f"Failed to get username with getpass: {e}")
        # Fallback for some environments where getpass might fail (e.g. no controlling tty)
        try:
            username = os.environ.get('USER') or os.environ.get('LOGNAME') or "N/A (Env var not set)"
        except Exception as e_env:
            logging.error(f"Failed to get username from env vars: {e_env}")


    uid = os.getuid()
    gid = os.getgid()
    
    groups_str = "N/A"
    try:
        import grp
        group_names = [g.gr_name for g in [grp.getgrgid(gid)] + [grp.getgrgid(g) for g in os.getgroups()]]
        groups_str = ", ".join(sorted(list(set(group_names)))) # Unique, sorted
    except Exception as e:
        logging.warning(f"Could not get group names: {e}")
        groups_str = f"(Error: {e})"


    msg = (f"👤 **User Info on {DEVICE_NAME}**:\n"
           f"   - **Username**: {username}\n"
           f"   - **User ID (UID)**: {uid}\n"
           f"   - **Group ID (GID)**: {gid}\n"
           f"   - **Groups**: {groups_str}")
    await update.message.reply_text(msg, parse_mode='Markdown')

async def say_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_command("say", update.effective_user, context.args)
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized user.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /say [message]")
        return
    
    message_to_speak = " ".join(context.args)
    # Basic sanitization to prevent command injection if message is used directly in shell=True
    # Though for most TTS commands here, message is an argument.
    # For festival, it's stdin, which is safer.
    # For pico2wave piped to aplay, if message were part of filename, it'd be risky.
    # Here, it's an argument to pico2wave, safer.
    
    current_env = get_wayland_env() # Though TTS usually doesn't need Wayland env.

    tts_methods = []
    # Ordered by perceived quality or common availability. Adjust as needed.
    # espeak-ng is generally preferred over older espeak
    if check_command_exists("espeak-ng"):
        tts_methods.append({'name': 'espeak-ng', 'cmd_list': ["espeak-ng", "-a", "150", "-s", "160", message_to_speak]})
    # pico2wave (SVOX Pico) + aplay is often good quality
    if check_command_exists("pico2wave") and check_command_exists("aplay"):
        tts_methods.append({'name': 'pico2wave+aplay', 'type': 'pipe'}) # Special handling
    if check_command_exists("espeak"):
        tts_methods.append({'name': 'espeak', 'cmd_list': ["espeak", "-a", "150", "-s", "160", message_to_speak]})
    if check_command_exists("festival"):
        tts_methods.append({'name': 'festival', 'type': 'stdin'}) # Special handling
    # Add spd-say (speech-dispatcher) if you use it:
    # if check_command_exists("spd-say"):
    # tts_methods.append({'name': 'spd-say', 'cmd_list': ["spd-say", "--wait", message_to_speak]})


    if not tts_methods:
        await update.message.reply_text(f"❌ No Text-to-Speech (TTS) engines found on {DEVICE_NAME}. Please install espeak-ng, pico2wave, espeak, or festival.")
        return

    spoken = False
    for method_info in tts_methods:
        tool_name = method_info['name']
        logging.info(f"Attempting TTS with '{tool_name}'")
        try:
            if method_info.get('type') == 'pipe': # For pico2wave + aplay
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_wav_file:
                    wav_filepath = tmp_wav_file.name
                
                pico_cmd = ["pico2wave", "--wave", wav_filepath, message_to_speak]
                pico_proc = subprocess.run(pico_cmd, env=current_env, check=True, capture_output=True, text=True, timeout=5)
                logging.info(f"pico2wave for '{tool_name}' successful. Output: {pico_proc.stdout.strip()}")

                aplay_cmd = ["aplay", "-q", wav_filepath] # -q for quiet
                aplay_proc = subprocess.run(aplay_cmd, env=current_env, check=True, capture_output=True, text=True, timeout=10)
                logging.info(f"aplay for '{tool_name}' successful. Output: {aplay_proc.stdout.strip()}")
                
                os.remove(wav_filepath)
                spoken = True

            elif method_info.get('type') == 'stdin': # For festival
                festival_proc = subprocess.Popen(["festival", "--tts"], stdin=subprocess.PIPE, env=current_env, text=True)
                stdout, stderr = festival_proc.communicate(input=message_to_speak, timeout=10)
                if festival_proc.returncode == 0:
                    logging.info(f"Festival TTS for '{tool_name}' successful.")
                    spoken = True
                else:
                    logging.warning(f"Festival TTS for '{tool_name}' failed with code {festival_proc.returncode}. Stderr: {stderr}")
            
            else: # Standard command execution
                cmd_list = method_info['cmd_list']
                proc = subprocess.run(cmd_list, env=current_env, check=True, capture_output=True, text=True, timeout=10)
                logging.info(f"TTS with '{tool_name}' successful. Output: {proc.stdout.strip()}")
                spoken = True
            
            if spoken:
                await update.message.reply_text(f"{DEVICE_NAME} 📢: '{message_to_speak}' (via {tool_name})")
                break # Exit loop on first success

        except subprocess.CalledProcessError as e:
            logging.warning(f"TTS method '{tool_name}' failed (CalledProcessError): {e.cmd}, RC: {e.returncode}, Stderr: {e.stderr.strip()}")
        except subprocess.TimeoutExpired:
            logging.warning(f"TTS method '{tool_name}' timed out.")
        except FileNotFoundError: # Should be caught by check_command_exists, but as a safeguard
             logging.error(f"TTS tool for '{tool_name}' not found at runtime, though check_command_exists passed.")
        except Exception as e:
            logging.error(f"An unexpected error occurred with TTS method '{tool_name}': {e}")
        finally:
            if 'wav_filepath' in locals() and os.path.exists(wav_filepath): # Ensure temp WAV is cleaned up
                try:
                    os.remove(wav_filepath)
                except OSError: pass


    if not spoken:
        await update.message.reply_text(f"❌ Failed to speak message on {DEVICE_NAME} using available TTS engines. Check logs for details.")


async def camera_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_command("camera", update.effective_user, context.args)
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized user.")
        return
    
    await update.message.reply_text(f"{DEVICE_NAME}: Accessing camera...")
    
    camera_devices_found = []
    # Try v4l2-ctl first if available for a more reliable list
    if check_command_exists("v4l2-ctl"):
        try:
            # Use a timeout for v4l2-ctl as it can sometimes hang on problematic devices
            result = subprocess.run(["v4l2-ctl", "--list-devices"], 
                                   capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                logging.info(f"v4l2-ctl --list-devices output:\n{result.stdout}")
                # Parse output: device paths are usually on lines following a device name line.
                # Example: "Some Camera (usb-xxxx): \n\t/dev/video0\n\t/dev/video1"
                current_device_name = None
                for line in result.stdout.split('\n'):
                    line_stripped = line.strip()
                    if not line_stripped: continue

                    if not line.startswith('\t') and ':' in line: # Likely a device name line
                        current_device_name = line_stripped
                    elif line.startswith('\t') and '/dev/video' in line_stripped: # Actual device path
                        if line_stripped not in camera_devices_found: # Avoid duplicates
                             camera_devices_found.append(line_stripped)
                             logging.info(f"Found camera device: {line_stripped} (under {current_device_name or 'Unknown Device'})")
            else:
                logging.warning(f"v4l2-ctl --list-devices failed with code {result.returncode}. Stderr: {result.stderr.strip()}")
        except subprocess.TimeoutExpired:
            logging.warning("v4l2-ctl --list-devices timed out.")
        except Exception as e:
            logging.warning(f"Failed to get camera list using v4l2-ctl: {e}")
    
    # If v4l2-ctl failed or not available, or found nothing, try common device paths
    if not camera_devices_found:
        logging.info("v4l2-ctl found no devices or failed. Probing common /dev/videoX paths.")
        for i in range(10): # Check /dev/video0 to /dev/video9
            device_path = f"/dev/video{i}"
            if os.path.exists(device_path):
                if device_path not in camera_devices_found:
                    camera_devices_found.append(device_path)
                    logging.info(f"Found camera device by probing: {device_path}")
    
    if not camera_devices_found:
        logging.warning("No camera devices found after v4l2-ctl and probing.")
        await update.message.reply_text(f"❌ No camera devices found on {DEVICE_NAME}.")
        return
    
    logging.info(f"Attempting to capture from camera devices: {camera_devices_found}")
    
    image_captured = False
    captured_from_device = None
    tmp_image_filepath = os.path.join(tempfile.gettempdir(), f"camera_img_{DEVICE_NAME}_{int(time.time())}.png")

    for device_path in camera_devices_found:
        # Extract numeric ID if possible, otherwise pass full path if OpenCV supports it (it often does)
        device_id_for_cv = device_path 
        try:
            # Try to convert /dev/videoX to integer X for OpenCV
            if device_path.startswith("/dev/video"):
                device_id_for_cv = int(device_path.replace('/dev/video', ''))
        except ValueError:
            logging.info(f"Could not parse integer ID from {device_path}, passing path directly to OpenCV.")


        logging.info(f"Trying camera: {device_path} (OpenCV ID: {device_id_for_cv})")
        cap = None # Ensure cap is defined for finally block
        try:
            # Try different APIs if default fails, e.g., cv2.CAP_V4L2
            cap = cv2.VideoCapture(device_id_for_cv, cv2.CAP_V4L2) 
            if not cap.isOpened():
                logging.warning(f"Failed to open camera {device_path} with V4L2 API, trying default API.")
                cap.release() # Release previous attempt
                cap = cv2.VideoCapture(device_id_for_cv) # Try default API
            
            if not cap.isOpened():
                logging.warning(f"Still failed to open camera {device_path} with default API.")
                if cap: cap.release()
                continue # Try next camera
                
            # Set common resolutions, camera will pick closest if exact not supported
            # Some cameras are slow to initialize, so setting props might take time or fail.
            # It's often better to read a few frames first.
            # cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            # cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            
            # Read a few frames to allow camera to adjust (autofocus, autoexposure)
            # And to discard initial blank/corrupted frames some cameras send
            for _ in range(5): # Read 5 frames
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.1) # Brief pause if read fails early
            
            if ret and frame is not None and frame.size > 0:
                # OpenCV captures in BGR by default. No need to convert to RGB for imwrite.
                # frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) # Not needed if writing BGR
                cv2.imwrite(tmp_image_filepath, frame) # imwrite expects BGR
                
                if os.path.exists(tmp_image_filepath) and os.path.getsize(tmp_image_filepath) > 0:
                    image_captured = True
                    captured_from_device = device_path
                    logging.info(f"Image captured successfully from {device_path} to {tmp_image_filepath}")
                    break # Success, exit loop
                else:
                    logging.warning(f"cv2.imwrite seemed to succeed for {device_path} but file is missing or empty.")
            else:
                logging.warning(f"Failed to retrieve a valid frame from {device_path} after several attempts. ret={ret}, frame is None or empty.")
                
        except Exception as e:
            logging.error(f"Exception while capturing from camera {device_path}: {e}")
        finally:
            if cap and cap.isOpened():
                cap.release()
    
    if image_captured and os.path.exists(tmp_image_filepath):
        try:
            with open(tmp_image_filepath, "rb") as photo_file:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id, 
                    photo=photo_file,
                    caption=f"Camera image from {DEVICE_NAME} (via {captured_from_device})"
                )
            logging.info("Camera image sent successfully.")
        except Exception as e:
            logging.error(f"Failed to send camera image: {e}")
            await update.message.reply_text(f"❌ Failed to send image: {str(e)}")
        finally:
            if os.path.exists(tmp_image_filepath):
                try:
                    os.remove(tmp_image_filepath)
                except OSError as e:
                     logging.warning(f"Could not remove temporary camera image {tmp_image_filepath}: {e}")
    elif not image_captured:
        await update.message.reply_text(f"❌ Failed to capture image from any camera on {DEVICE_NAME}. Check logs.")


async def shutdown_bot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_command("shutdown_bot", update.effective_user)
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized user.")
        return
    await update.message.reply_text(f"{DEVICE_NAME}: 🛑 Bot is shutting down...")
    logging.info("Shutdown_bot command received. Initiating bot shutdown sequence.")
    
    # Gracefully stop the application. This allows pending tasks to complete.
    # Ensure this is awaited if called from an async context, or run in a separate thread if from sync.
    # For telegram.ext, application.stop() is not async.
    # application.stop() # This would typically be called from the main thread or a signal handler context
    
    # To stop the polling loop from within a handler, we need a more direct approach
    # or signal the main thread. `os._exit()` is abrupt.
    # A gentler way is to tell the updater to stop.
    
    # Schedule the stop via the job queue to run after this handler completes
    context.application.create_task(context.application.stop_polling())
    logging.info("Scheduled application.stop_polling(). Bot will exit after current updates are processed.")
    # os._exit(0) # Avoid os._exit as it's too abrupt and skips atexit handlers.
    # The application should exit gracefully once polling stops.
    # If you need to ensure the entire script exits, atexit cleanup is preferred.
    # The main `application.run_polling()` will terminate when stop_polling() is effective.
    # If this isn't enough, `sys.exit(0)` could be called from the main thread after run_polling returns.
    # For now, rely on stop_polling() and the natural end of run_polling.


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors caused by updates."""
    logging.error(f"Update {update} caused error {context.error}", exc_info=context.error) # Add exc_info for full traceback
    
    # Optionally, send a message to the user if it's a user-facing error and update object is valid
    if isinstance(update, Update) and update.effective_message:
        try:
            error_message = f"❌ An error occurred while processing your request on {DEVICE_NAME}.\n"
            error_message += f"Error: {context.error}\n"
            # Be cautious about sending detailed error messages to users for security.
            # error_message += f"Type: {type(context.error).__name__}"
            await update.effective_message.reply_text(error_message)
        except Exception as e:
            logging.error(f"Failed to send error message to user: {e}")


if __name__ == "__main__":
    application = None # Define application in the outer scope for finally block
    try:
        # Check if another instance is running
        check_single_instance() # This will sys.exit if another instance is found
        
        print("Building Telegram bot application...")
        # Increase connect_timeout and read_timeout for more resilience
        application = (
            ApplicationBuilder()
            .token(BOT_TOKEN)
            .connect_timeout(30) # Seconds to wait for establishing a connection
            .read_timeout(30)    # Seconds to wait for a response after a request is made
            .pool_timeout(30)    # Timeout for getting a connection from the connection pool
            .build()
        )
        
        # Add error handler
        application.add_error_handler(error_handler)
        
        print("Registering command handlers...")
        application.add_handler(CommandHandler("shutdown", shutdown_command))
        application.add_handler(CommandHandler("shutdown_in", shutdown_in_command))
        application.add_handler(CommandHandler("cancel_shutdown", cancel_shutdown_command))
        application.add_handler(CommandHandler("restart", restart_command))
        application.add_handler(CommandHandler("lock", lock_command))
        application.add_handler(CommandHandler("status", status_command))
        application.add_handler(CommandHandler("screenshot", screenshot_command))
        application.add_handler(CommandHandler("whoami", whoami_command))
        application.add_handler(CommandHandler("say", say_command))
        application.add_handler(CommandHandler("camera", camera_command))
        application.add_handler(CommandHandler("shutdown_bot", shutdown_bot_command))
        
        logging.info(f"✅ {DEVICE_NAME} Bot is starting up...")
        print(f"✅ {DEVICE_NAME} Bot is running...")
        
        # For backward compatibility, if any part of your code might still expect `app`
        app = application 
        
        # Run the application
        # drop_pending_updates=True can be useful on first start after downtime
        # Consider allowed_updates to specify which update types your bot should receive.
        application.run_polling(
            timeout=30, # Long polling timeout
            drop_pending_updates=True, 
            # allowed_updates=Update.ALL_TYPES # Or specify: [Update.MESSAGE, Update.CALLBACK_QUERY]
        )

    except SystemExit: # Raised by check_single_instance or signal_handler
        logging.info("SystemExit caught. Bot is shutting down as intended.")
    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt received. Shutting down bot...")
        print("\nBot shutting down (KeyboardInterrupt)...")
    except Exception as e:
        logging.critical(f"CRITICAL: Failed to start or run bot: {e}", exc_info=True)
        # Ensure PID file is cleaned up if this instance created it and failed critically
        # The atexit handler should cover this, but an explicit check here might be useful
        # if atexit doesn't run due to how the exception is handled or an os._exit() call somewhere.
    finally:
        logging.info(f"{DEVICE_NAME} Bot has stopped or failed to start.")
        if application and application.updater and application.updater.is_running:
            logging.info("Ensuring bot polling is stopped in finally block...")
            application.stop_polling() # This will signal run_polling to exit
        
        # The atexit registered `cleanup` function will handle PID file removal.
        # Avoid calling cleanup() directly here if atexit is expected to run, to prevent double-removal issues.
        print(f"{DEVICE_NAME} Bot has exited.")
