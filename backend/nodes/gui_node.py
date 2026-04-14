"""
GUI Automation Nodes
  GUIAutomationNode  – pyautogui: mouse, keyboard, hotkeys, typing
  AppControlNode     – pywinauto: find and interact with any Windows app by title
"""
import time
import logging
from .base import BaseNode
from backend.config import ALLOWED_APPS, GUI_SAFE_MODE, ALLOWED_MOUSE_AREA, BLOCKED_KEYS

logger = logging.getLogger(__name__)


class GUIAutomationNode(BaseNode):
    node_type = "GUI_AUTOMATION"
    risk_level = "HIGH"

    def execute(self, params: dict, context: dict) -> str:
        try:
            import pyautogui
            pyautogui.FAILSAFE = True  # move mouse to top-left corner to abort
        except ImportError:
            return "GUI_AUTOMATION: 'pyautogui' is not installed."

        actions = params.get("actions", [])
        if isinstance(actions, str):
            # Allow simple shorthand like "type:Hello World"
            actions = [{"type": "type", "text": actions}]

        results = []
        delay = float(params.get("delay", 0.3))

        for step in actions:
            action_type = step.get("type", "").lower()
            try:
                if action_type == "type":
                    text_to_type = step.get("text", "")
                    logger.info(f"GUI Type: {text_to_type[:30]}")
                    pyautogui.write(text_to_type, interval=0.05)
                    results.append(f"Typed: {text_to_type[:30]}")

                elif action_type == "press":
                    key = step.get("key", "enter").lower()
                    if GUI_SAFE_MODE and key in BLOCKED_KEYS:
                        raise PermissionError(f"Sandboxing blocked destructive key press: '{key}'")
                    logger.info(f"GUI Press: {key}")
                    pyautogui.press(key)
                    results.append(f"Pressed: {key}")

                elif action_type == "hotkey":
                    keys = [k.lower() for k in step.get("keys", [])]
                    if GUI_SAFE_MODE and any(k in BLOCKED_KEYS for k in keys):
                        raise PermissionError(f"Sandboxing blocked destructive hotkey: {keys}")
                    logger.info(f"GUI Hotkey: {keys}")
                    pyautogui.hotkey(*keys)
                    results.append(f"Hotkey: {'+'.join(keys)}")

                elif action_type == "click":
                    x = step.get("x")
                    y = step.get("y")
                    logger.info(f"GUI Click: x={x}, y={y}")
                    if GUI_SAFE_MODE and x is not None and y is not None:
                        if not (ALLOWED_MOUSE_AREA[0] <= x <= ALLOWED_MOUSE_AREA[2] and ALLOWED_MOUSE_AREA[1] <= y <= ALLOWED_MOUSE_AREA[3]):
                            raise PermissionError(f"Sandboxing blocked click outside allowed area: ({x}, {y})")
                    if x and y:
                        pyautogui.click(x, y)
                        results.append(f"Clicked ({x}, {y})")
                    else:
                        pyautogui.click()
                        results.append("Clicked current position")

                elif action_type == "move":
                    x = step.get("x", 0)
                    y = step.get("y", 0)
                    logger.info(f"GUI Move: x={x}, y={y}")
                    if GUI_SAFE_MODE:
                        if not (ALLOWED_MOUSE_AREA[0] <= x <= ALLOWED_MOUSE_AREA[2] and ALLOWED_MOUSE_AREA[1] <= y <= ALLOWED_MOUSE_AREA[3]):
                            raise PermissionError(f"Sandboxing blocked move outside allowed area: ({x}, {y})")
                    pyautogui.moveTo(x, y, duration=0.5)
                    results.append(f"Moved to ({x}, {y})")

                elif action_type == "screenshot":
                    from pathlib import Path
                    import os
                    out_dir = Path(os.getenv("OUTPUT_DIR", r"D:\GENAI\AI-workflow builder\outputs"))
                    out_dir.mkdir(parents=True, exist_ok=True)
                    path = str(out_dir / "gui_screenshot.png")
                    pyautogui.screenshot(path)
                    results.append(f"Screenshot saved: {path}")

                elif action_type == "wait":
                    secs = float(step.get("seconds", 1))
                    time.sleep(secs)
                    results.append(f"Waited {secs}s")

                time.sleep(delay)

            except Exception as step_err:
                results.append(f"Step '{action_type}' failed: {str(step_err)}")

        return "GUI actions completed:\n" + "\n".join(f"  • {r}" for r in results)


class AppControlNode(BaseNode):
    node_type = "APP_CONTROL"
    risk_level = "HIGH"

    def execute(self, params: dict, context: dict) -> str:
        try:
            from pywinauto import Application, findwindows
        except ImportError:
            return "APP_CONTROL: 'pywinauto' is not installed."

        app_title = params.get("app_title", "")
        actions = params.get("actions", [])

        if not app_title:
            return "APP_CONTROL: 'app_title' is required (e.g. 'Notepad', 'Microsoft Word')."
            
        app_title_lower = app_title.lower()
        is_allowed = False
        for allowed in ALLOWED_APPS:
            allowed_base = allowed.replace(".exe", "")
            if allowed_base in app_title_lower or app_title_lower in allowed_base:
                is_allowed = True
                break
                
        if not is_allowed:
            return f"APP_CONTROL: Sandboxing blocked interaction with unauthorized application title: '{app_title}'"

        try:
            # Connect to an already-running window
            app = Application(backend="uia").connect(title_re=f".*{app_title}.*", timeout=5)
            window = app.top_window()
            window.set_focus()

            results = []
            for step in actions:
                action_type = step.get("type", "").lower()

                if action_type == "type":
                    logger.info(f"AppControl Type: {step.get('text', '')[:30]}")
                    window.type_keys(step.get("text", ""), with_spaces=True)
                    results.append(f"Typed: {step.get('text', '')[:30]}")

                elif action_type == "click_button":
                    logger.info(f"AppControl Click Button: {step.get('button')}")
                    btn = window.child_window(title=step.get("button"), control_type="Button")
                    btn.click()
                    results.append(f"Clicked button: {step.get('button')}")

                elif action_type == "menu":
                    menu_path = step.get("path", "")
                    logger.info(f"AppControl Menu: {menu_path}")
                    window.menu_select(menu_path)
                    results.append(f"Menu: {menu_path}")

                time.sleep(0.4)

            return f"APP_CONTROL on '{app_title}':\n" + "\n".join(f"  • {r}" for r in results)

        except Exception as e:
            return f"APP_CONTROL: Could not control '{app_title}': {str(e)}"
