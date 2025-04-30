@echo off
chcp 65001 > nul
cd /d C:\Users\varad\daemon\ControlMyPC\Windows
"C:\Users\varad\AppData\Local\Programs\Python\Python311\pythonw.exe" -u "C:\Users\varad\daemon\ControlMyPC\Windows\RemoteDeactivationWindows.py" >> startup_log.txt 2>> error_log.txt