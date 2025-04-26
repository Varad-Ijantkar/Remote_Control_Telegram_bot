# ControlMyPC

ControlMyPC is a Telegram bot that allows you to remotely control your PC using commands. It supports both Windows and Linux platforms, with separate scripts for each operating system. You can perform actions like shutting down, restarting, locking the screen, taking screenshots, capturing camera images, and more—all through Telegram.

## Features

- **Cross-Platform Support:** Works on both Windows and Linux.
- **Remote Commands:**
  - `/shutdown`: Shut down the PC immediately.
  - `/shutdown_in [seconds]`: Schedule a shutdown.
  - `/cancel_shutdown`: Cancel a scheduled shutdown.
  - `/restart`: Restart the PC.
  - `/lock`: Lock the screen.
  - `/status`: Check system status (uptime, battery, power status).
  - `/screenshot`: Take a screenshot and send it via Telegram.
  - `/whoami`: Display the current username.
  - `/say [message]`: Speak a message using text-to-speech.
  - `/camera`: Capture an image from the webcam and send it.
  - `/shutdown_bot`: Stop the bot.

## Prerequisites

- A Telegram account and a bot token (create a bot via [@BotFather](https://t.me/BotFather)).
- Python 3.6+
- Git (optional)

## Setup Instructions

### 1. Clone the Repository

```bash
git clone https://github.com/Varad-Ijantkar/ControlMyPC.git
cd ControlMyPC
```

### 2. Set Up Environment Variables

Create a `.env` file in the appropriate directory:

For Windows: `windows/.env.w11`

For Linux: `linux/.env.arch`

Add the following content:

```
BOT_TOKEN=your_bot_token_here
ALLOWED_USER_ID=your_telegram_user_id_here
DEVICE_NAME=your_device_name_here
```

Example (Windows):

```bash
cd windows
echo BOT_TOKEN=your_bot_token_here > .env.w11
echo ALLOWED_USER_ID=your_telegram_user_id_here >> .env.w11
echo DEVICE_NAME=MyWindowsPC >> .env.w11
```

Example (Linux):

```bash
cd linux
echo "BOT_TOKEN=your_bot_token_here" > .env.linux
echo "ALLOWED_USER_ID=your_telegram_user_id_here" >> .env.linux
echo "DEVICE_NAME=MyLinuxPC" >> .env.linux
```

### 3. Platform-Specific Setup

#### Windows Setup

- Navigate to the windows directory:

```bash
cd windows
```

- Install dependencies:

```bash
pip install python-telegram-bot psutil pyautogui pillow pyttsx3 opencv-python python-dotenv
```

- Run the bot manually:

```bash
python remote_bot_win.py
```

- **Automate with Task Scheduler:**

Create a batch file:

```bash
echo @echo off > start_remote_bot.bat
echo cd C:\Users\yourusername\ControlMyPC\windows >> start_remote_bot.bat
echo python remote_bot_win.py >> C:\Users\yourusername\ControlMyPC\windows\RemoteDeactivation.log 2>&1 >> start_remote_bot.bat
echo exit >> start_remote_bot.bat
```

Set it up in Task Scheduler with the following settings:

- **Trigger:** At startup, delay 5 seconds
- **Action:** Run `start_remote_bot.bat`
- **Settings:** Allow task to be run on demand, restart if fails

#### Linux Setup (Arch Linux)

- Navigate to the linux directory:

```bash
cd linux
```

- Install dependencies:

```bash
sudo pacman -S python python-pip
yay -S grim espeak-ng # if using Wayland and for /say command
pip install -r requirements_linux.txt
```

- Move script to system path:

```bash
sudo cp remote_bot_linux.py /usr/local/bin/
sudo chmod +x /usr/local/bin/remote_bot_linux.py
sudo mkdir -p /etc/ControlMyPC
sudo cp .env.arch /etc/ControlMyPC/
```

- Create a systemd service:

```bash
sudo nano /etc/systemd/system/ControlMyPC.service
```

Add:

```ini
[Unit]
Description=ControlMyPC Telegram Bot
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/remote_bot_linux.py
Restart=always
User=your_username
EnvironmentFile=/etc/ControlMyPC/.env.arch
WorkingDirectory=/usr/local/bin/

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable ControlMyPC.service
sudo systemctl start ControlMyPC.service
```

Check status:

```bash
systemctl status ControlMyPC.service
```

## Usage

- Start a chat with your Telegram bot.
- Send commands like `/status`, `/screenshot`, `/shutdown`, etc.
- Only the user with the `ALLOWED_USER_ID` can interact with the bot.

## Troubleshooting

- **Bot Not Responding:**
  - Check logs:
    - Windows: `C:\Users\yourusername\ControlMyPC\windows\RemoteDeactivation.log`
    - Linux: `/home/your_username/Services/RemoteDeactivation.log`
  - Verify `.env` values are correct.

- **Screenshot Issues:**
  - Windows: Ensure session permissions.
  - Linux: Install `grim` if using Wayland.

- **Lock/Say Failures:**
  - Windows: User session permissions.
  - Linux: Run service as user, not root.

## Contributing

Feel free to fork this repository, make improvements, and submit a pull request. Issues and feature requests are welcome!
