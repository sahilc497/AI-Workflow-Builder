"""
WhatsAppNode – Send a WhatsApp message by contact name using Playwright.

The user must be logged into WhatsApp Web in their default Chrome profile.
No phone numbers needed — just the contact name as it appears in WhatsApp.
"""
import time
from .base import BaseNode


class WhatsAppNode(BaseNode):
    node_type = "WHATSAPP_MESSAGE"

    def validate(self, params: dict) -> None:
        if not params.get("contact"):
            raise ValueError("WHATSAPP_MESSAGE: 'contact' (name) is required.")
        if not params.get("message"):
            raise ValueError("WHATSAPP_MESSAGE: 'message' is required.")

    def execute(self, params: dict, context: dict) -> str:
        contact = params.get("contact", "").strip()
        message = params.get("message", "").strip()

        # Allow message to be built from context
        msg_ref = params.get("message_ref")
        if msg_ref and msg_ref in context:
            message = str(context[msg_ref])

        if not contact or not message:
            return "WHATSAPP_MESSAGE: contact and message are both required."

        try:
            import pyautogui
            import os
            
            # Launch the native Windows WhatsApp app
            os.system('start whatsapp:')
            # Wait for the app to open and come to the foreground
            time.sleep(5)
            
            # Reset UI State:
            # 1. Press Esc a couple of times to close out of any open menus or overlays
            pyautogui.press('esc', presses=2, interval=0.2)
            time.sleep(0.5)
            
            # 2. Switch to the main "Chats" tab (Ctrl+1)
            pyautogui.hotkey('ctrl', '1')
            time.sleep(0.5)
            
            # 3. Focus the search bar
            pyautogui.hotkey('ctrl', 'f')
            time.sleep(1)
            
            # 4. Clear any previous search (Select all -> Backspace)
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.2)
            pyautogui.press('backspace')
            time.sleep(0.5)
            
            # Type contact name
            pyautogui.write(contact)
            time.sleep(2) # Give time for search results
            
            # Navigate to the first result
            # Pressing 'down' moves focus from the search box to the first search result
            pyautogui.press('down')
            time.sleep(0.5)
            pyautogui.press('enter')
            time.sleep(1.5)
            
            # Type the message
            pyautogui.write(message)
            time.sleep(0.5)
            
            # Send
            pyautogui.press('enter')
            
            return f"✅ Sent message to '{contact}' using WhatsApp Desktop App."
            
        except Exception as e:
            return f"WhatsApp Desktop automation failed: {str(e)}"
