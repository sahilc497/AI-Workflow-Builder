import os

# Desktop & GUI Sandboxing configuration
ALLOWED_APPS_DEFAULT = "whatsapp.exe,chrome.exe,notepad.exe,winword.exe,excel.exe,powerpnt.exe,msedge.exe,firefox.exe,explorer.exe,calc.exe,mspaint.exe"
ALLOWED_APPS_STR = os.getenv("ALLOWED_APPS", ALLOWED_APPS_DEFAULT)
ALLOWED_APPS = [app.strip().lower() for app in ALLOWED_APPS_STR.split(",")]

GUI_SAFE_MODE = os.getenv("GUI_SAFE_MODE", "true").lower() == "true"
ALLOWED_MOUSE_AREA = (0, 0, 1920, 1080)  # (x1, y1, x2, y2) bounds
BLOCKED_KEYS = {"f4", "delete", "del", "win", "winleft", "winright", "cmd", "command", "alt"} # Restricted keys
