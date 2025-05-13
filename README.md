# Remote Control Telegram Bot

Remotely control your Linux (with a focus on Hyprland) and Windows systems via a secure Telegram bot. Perform actions like shutdown, restart, lock screen, take screenshots, get system status, and more.

## Features

The bot supports the following commands on both Linux and Windows (with platform-specific implementations):

* **Power Management:**
    * `/shutdown`: Immediately shuts down the machine.
    * `/shutdown_in <seconds>`: Schedules a shutdown after the specified number of seconds.
    * `/cancel_shutdown`: Cancels any pending scheduled shutdown.
    * `/restart`: Immediately restarts the machine.
* **Session & System:**
    * `/lock`: Locks the workstation.
    * `/status`: Provides system status (uptime, CPU, memory, battery, power).
    * `/whoami`: Shows the username under which the bot script is running.
* **Interactive:**
    * `/screenshot`: Takes a screenshot of the current display and sends it.
    * `/say <message>`: Uses Text-to-Speech to make the machine speak the provided message.
    * `/camera`: Captures an image from the primary webcam and sends it.
* **Bot Control:**
    * `/shutdown_bot`: Stops the bot script itself.

## Prerequisites

* Python 3.7+
* A Telegram Bot Token (get one from BotFather on Telegram).
* Git (for cloning the repository).
* Administrative/sudo access may be required on Linux for setting up Polkit rules and on Windows for some system-level configurations (like Task Scheduler for autostart if not using Startup folder).

## Setup Instructions

### A. Common Steps (For Both Linux and Windows)

1.  **Clone the Repository:**
    ```bash
    git clone <your-repository-url>
    cd <your-repository-name>
    ```

2.  **Create a Virtual Environment (Recommended):**
    ```bash
    python -m venv venv
    # Activate it:
    # On Linux/macOS:
    source venv/bin/activate
    # On Windows (cmd.exe):
    venv\Scripts\activate.bat
    # On Windows (PowerShell):
    venv\Scripts\Activate.ps1
    ```

3.  **Install Common Python Libraries:**
    ```bash
    pip install python-telegram-bot python-dotenv psutil opencv-python
    ```
    *(Note: `opencv-python` is used for the `/camera` command on both platforms. The Linux script also uses it for `/camera`.)*

4.  **Create and Configure the `.env` File:**
    The bot requires an environment file to store your Telegram Bot Token and authorized user ID. The scripts look for this file in specific locations:
    * **Linux:** `~/Services/.env.linux`
    * **Windows:** `~/daemon/ControlMyPC/Windows/.env.w11` (where `~` is your user home directory, e.g., `C:\Users\YourUser`)

    Create the respective directory and the `.env` file inside it. The content should be:
    ```ini
    BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN_HERE
    ALLOWED_USER_ID=YOUR_TELEGRAM_USER_ID_HERE
    DEVICE_NAME=MyCoolPC_or_MyLinuxBox 
    ```
    * Replace `YOUR_TELEGRAM_BOT_TOKEN_HERE` with the token you got from BotFather.
    * Replace `YOUR_TELEGRAM_USER_ID_HERE` with your numerical Telegram User ID. You can get this from bots like `@userinfobot` on Telegram. Only this user will be able to issue commands.
    * `DEVICE_NAME` is a friendly name for your device that will appear in bot messages.

    Ensure the log directories are also created or allow the script to create them:
    * **Linux:** `~/Services/` (script creates `RemoteDeactivation.log` inside)
    * **Windows:** `~/daemon/ControlMyPC/Windows/` (script creates `RemoteDeactivation.log` inside)

### B. Linux Specific Setup (Hyprland/Wayland Focus)

The Linux script (`RemoteDeactivationLinux.py`) is tailored for modern Linux desktops, especially those using Wayland and systemd.

1.  **Additional System Dependencies:**
    You'll need to install various command-line utilities that the script uses. The exact package names might vary slightly based on your distribution (e.g., Arch Linux, Ubuntu).

    * **Wayland Screenshot/Lock Tools:**
        * `grim` and `grimblast` (for screenshots, `grimblast` is often Hyprland-friendly)
        * `hyprshot` (if using Hyprland and `grimblast` is not preferred)
        * `swaylock` or `hyprlock` (for screen locking)
        * `hyprctl` (if using Hyprland, for dispatching commands)
    * **Text-to-Speech (TTS) Engines (install at least one):**
        * `espeak-ng` (recommended)
        * `pico2wave` (from `libttspico-utils` or similar) and `aplay` (from `alsa-utils`)
        * `festival`
    * **Camera Utilities:**
        * `v4l2-ctl` (from `v4l-utils`) for better camera device discovery.
    * **General Utilities:**
        * `pkill` (usually part of `procps` or `procps-ng`)
        * `shutil` (Python module, but ensure core utils providing `which` are present)

    Example installation on Arch Linux:
    ```bash
    sudo pacman -S grim grimblast hyprshot hyprlock swaylock hyprctl \
                   espeak-ng svox-pico alsa-utils festival \
                   v4l-utils procps-ng systemd # systemd provides loginctl, systemctl
    ```
    Example installation on Debian/Ubuntu:
    ```bash
    sudo apt update
    sudo apt install grim slurp # grimblast/hyprshot might need manual install or come from other sources
                   # For hyprlock/swaylock, check your Hyprland documentation for installation.
                   espeak-ng libttspico-utils alsa-utils festival \
                   v4l-utils procps systemd # systemd is core
    ```

2.  **Systemd User Service Setup (for Autostart and Background Operation):**
    This is the recommended way to run the bot.

    * Create the service file at `~/.config/systemd/user/RemoteControl.service`:
        ```systemd
        [Unit]
        Description=Remote Control Service (Linux User)
        After=graphical-session.target network-online.target
        PartOf=graphical-session.target

        [Service]
        Type=simple
        WorkingDirectory=/path/to/your/project/RemoteDeactivationLinux # Adjust if script is elsewhere
        ExecStart=/path/to/your/project/venv/bin/python /path/to/your/project/RemoteDeactivationLinux.py
        Restart=always
        RestartSec=5

        [Install]
        WantedBy=graphical-session.target
        ```
        * Replace `/path/to/your/project/` with the actual path to where you cloned the repository.

    * Enable and manage the service (as your normal user, not root):
        ```bash
        systemctl --user daemon-reload
        systemctl --user enable RemoteControl.service
        systemctl --user start RemoteControl.service

        # To check status:
        systemctl --user status RemoteControl.service
        # To view logs:
        journalctl --user -u RemoteControl.service -f
        ```

3.  **Hyprland Configuration (for Environment Import):**
    To ensure the bot's systemd user service can interact with your Hyprland session (for screenshots, locking), add this to your Hyprland configuration. If you use HyDE, place this in `~/.config/hypr/userprefs.conf`. Otherwise, add to your main `~/.config/hypr/hyprland.conf`:

    ```hyprlang
    # Import environment variables for systemd user services & start the bot
    exec-once = systemctl --user import-environment DISPLAY WAYLAND_DISPLAY XDG_RUNTIME_DIR DBUS_SESSION_BUS_ADDRESS HYPRLAND_INSTANCE_SIGNATURE SWAYSOCK XDG_SESSION_TYPE XDG_CURRENT_DESKTOP XDG_SEAT XDG_VTNR
    exec-once = systemctl --user start RemoteControl.service # Optional if service is already enabled via WantedBy
    ```

4.  **Polkit Rules (for Passwordless Shutdown/Restart/Lock):**
    For commands like `/shutdown`, `/restart`, and potentially `/lock` (if using `loginctl lock-session`), you'll need Polkit rules to allow the user running the bot to perform these actions without a password.
    Create `/etc/polkit-1/rules.d/50-remotecontrol-bot.rules` (as root):
    ```javascript
    // /etc/polkit-1/rules.d/50-remotecontrol-bot.rules
    // Replace 'your_linux_username' with the username the bot runs as.
    polkit.addRule(function(action, subject) {
        if (subject.user == "your_linux_username") {
            if (action.id == "org.freedesktop.login1.power-off" ||
                action.id == "org.freedesktop.login1.power-off-multiple-sessions" ||
                action.id == "org.freedesktop.login1.reboot" ||
                action.id == "org.freedesktop.login1.reboot-multiple-sessions" ||
                action.id == "org.freedesktop.login1.lock-session" ||
                action.id == "org.freedesktop.login1.lock-sessions") {
                return polkit.Result.YES;
            }
        }
    });
    ```
    This allows `loginctl` and D-Bus methods to work without interactive authentication.

5.  **Troubleshooting `loginctl`:**
    If `/shutdown` or `/restart` commands using `loginctl` fail with "Unknown command verb," test `loginctl poweroff` directly in your terminal. If it also fails there, there's an issue with your system's `systemd` package or configuration that needs to be addressed at the OS level.

### C. Windows Specific Setup

The Windows script (`RemoteDeactivationWindows.py`) uses Windows-specific commands and libraries.

1.  **Additional Python Libraries:**
    ```bash
    pip install pyautogui pyttsx3 pypiwin32 # pypiwin32 for ctypes if not implicitly available
    ```
    * `pyautogui` for screenshots.
    * `pyttsx3` for Text-to-Speech.
    * `pypiwin32` provides access to Windows APIs; `ctypes` is built-in but `pypiwin32` can be a helpful wrapper.

2.  **Running the Script:**
    * **Manually:**
        Open Command Prompt or PowerShell, activate your virtual environment, and run:
        ```bash
        python C:\path\to\your\project\RemoteDeactivationWindows.py
        ```
    * **Using the `.bat` File:**
        A `.bat` file is provided to help run the script, especially in the background or at startup. Edit the `.bat` file to match your Python installation path and script path.

        Example `start_bot.bat` (generalize paths, do not hardcode your username):
        ```batch
        @echo off
        chcp 65001 > nul
        cd /d "C:\path\to\your\project"
        REM Ensure you use the pythonw.exe from your virtual environment if you created one
        REM Or provide the full path to your global pythonw.exe
        REM Example using a venv:
        REM "C:\path\to\your\project\venv\Scripts\pythonw.exe" -u "C:\path\to\your\project\RemoteDeactivationWindows.py" >> startup_log.txt 2>> error_log.txt
        REM Example using global Python:
        "C:\Path\To\Your\Python\Python3XX\pythonw.exe" -u "C:\path\to\your\project\RemoteDeactivationWindows.py" >> "%HOMEPATH%\daemon\ControlMyPC\Windows\startup_log.txt" 2>> "%HOMEPATH%\daemon\ControlMyPC\Windows\error_log.txt"
        ```
        * `pythonw.exe` runs the script without a visible console window.
        * `>> startup_log.txt 2>> error_log.txt` redirects standard output and errors to log files in the script's directory or a specified log directory.

3.  **Autostarting the `.bat` File on Windows:**
    To make the bot run when Windows starts:
    * **Startup Folder:**
        1.  Press `Win + R`, type `shell:startup`, and press Enter. This opens the Startup folder.
        2.  Create a shortcut to your `.bat` file and place it in this folder.
    * **Task Scheduler (More Control):**
        1.  Open Task Scheduler.
        2.  Create a new Basic Task.
        3.  Set it to trigger "When I log on" or "When the computer starts."
        4.  Set the action to "Start a program" and point it to your `.bat` file.
        5.  Configure other settings like running with highest privileges if needed (though usually not required if the script itself doesn't need admin for its core functions).

## Usage

Once the bot script is running on your Linux or Windows machine and you have configured the `.env` file with your `BOT_TOKEN` and `ALLOWED_USER_ID`:

1.  Open Telegram and find the bot you created with BotFather.
2.  Send commands to it, for example:
    * `/status`
    * `/screenshot`
    * `/say Hello from my computer!`
    * `/shutdown_in 300` (shuts down in 5 minutes)

Only messages from the `ALLOWED_USER_ID` will be processed.

## Troubleshooting

* **General:**
    * Ensure your `BOT_TOKEN` and `ALLOWED_USER_ID` are correct in the `.env` file.
    * Check the `RemoteDeactivation.log` file in the respective log directory (`~/Services/` on Linux, `~/daemon/ControlMyPC/Windows/` on Windows) for errors.
    * Ensure the machine running the bot has a stable internet connection.
* **Linux:**
    * **Permissions:** Polkit rules are crucial for shutdown/restart.
    * **Environment:** If lock/screenshot fails, ensure the systemd user service is correctly importing environment variables from Hyprland (`HYPRLAND_INSTANCE_SIGNATURE`, `DBUS_SESSION_BUS_ADDRESS`, `WAYLAND_DISPLAY`). Check `journalctl --user -u RemoteControl.service`.
    * **`loginctl` Issues:** If `loginctl` commands fail with "Unknown command verb," test them directly in your Hyprland terminal. This indicates a system-level issue with your `systemd` installation.
    * **Missing Tools:** Ensure all required command-line utilities are installed.
* **Windows:**
    * **Firewall:** Your system firewall might block the Python script from making outgoing connections to Telegram. Ensure it's allowed.
    * **`pyautogui` on Secure Desktops:** Screenshots might fail on certain secure screens (like UAC prompts or login screen). The script tries to take a screenshot of the active desktop.
    * **TTS Engine:** `pyttsx3` usually works out of the box with Windows SAPI5 voices. If `/say` fails, check if you have TTS voices installed in Windows.
    * **Camera Access:** Ensure no other application is exclusively using the camera.

## Contributing

Feel free to fork the project, make improvements, and submit pull requests. Please ensure your changes are compatible with both Linux and Windows platforms or are clearly marked as platform-specific.

## License

Consider adding a license file to your project (e.g., MIT License).
