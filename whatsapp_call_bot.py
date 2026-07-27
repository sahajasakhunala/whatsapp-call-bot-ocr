import os
import sys
import time
import json
import random
import re
import argparse
import logging
import winsound
import ctypes
import ctypes.wintypes
import threading
from pathlib import Path
from enum import Enum, auto

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("WhatsAppCallBot")

# Try to import external libraries and provide clear error messages if missing
try:
    import pyautogui
    import cv2
    import pytesseract
    import numpy as np
    import pygetwindow as gw
except ImportError as e:
    logger.error(f"Missing required library: {e}")
    logger.error("Please install dependencies: pip install -r requirements.txt")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Call Result State Machine Enum
# ---------------------------------------------------------------------------
class CallResult(Enum):
    ANSWERED = auto()
    NO_ANSWER = auto()
    DECLINED_OR_UNAVAILABLE = auto()
    USER_CANCELLED = auto()
    WINDOW_FAILED = auto()


# ---------------------------------------------------------------------------
# Global stop flag - set to True when user presses Esc anywhere
# ---------------------------------------------------------------------------
_stop_requested = False

# ---------------------------------------------------------------------------
# Configuration parameters
# ---------------------------------------------------------------------------
CONFIG_FILE = Path("whatsapp_config.json")
DEFAULT_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    r"C:\Users\{username}\AppData\Local\Programs\Tesseract-OCR\tesseract.exe",
    r"C:\Users\{username}\AppData\Local\Tesseract-OCR\tesseract.exe"
]

DEFAULT_CONFIG = {
    "call_button_1_coords": [1000, 100],
    "call_button_2_coords": [1000, 150],
    "video_call_button_1_coords": [1000, 100],
    "video_call_button_2_coords": [1000, 150],
    "end_call_coords": [960, 800],
    "timer_bbox": {
        "x": 920,
        "y": 750,
        "w": 80,
        "h": 30
    },
    "timeout_seconds": 25,
    "max_retries": 10,
    "cooldown_min_seconds": 2.0,
    "cooldown_max_seconds": 5.0,
    "tesseract_cmd": "",
    "sound_file": "",
    "call_type": "voice",
    "contact_name": ""
}

# ---------------------------------------------------------------------------
# Win32 RECT structure
# ---------------------------------------------------------------------------
class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


# ---------------------------------------------------------------------------
# Global Esc Hotkey Listener
# ---------------------------------------------------------------------------
VK_ESCAPE = 0x1B

def _esc_listener_loop():
    """Background thread: polls GetAsyncKeyState for Esc press. No focus required."""
    global _stop_requested
    user32 = ctypes.windll.user32
    while user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000:
        time.sleep(0.05)
    while True:
        if user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000:
            _stop_requested = True
            logger.warning("Esc pressed. Stopping bot cleanly...")
            return
        time.sleep(0.05)

def start_esc_listener():
    """Start the background Esc key listener thread."""
    t = threading.Thread(target=_esc_listener_loop, daemon=True, name="EscListener")
    t.start()

def check_stop():
    """Call this at safe points in the loop. Exits cleanly if Esc was pressed."""
    if _stop_requested:
        logger.info("Bot stopped by user (Esc key). Exiting cleanly.")
        sys.exit(0)

def interruptible_sleep(duration: float):
    """Sleeps in small 100ms increments to verify and react to Esc key presses instantly."""
    start = time.time()
    while time.time() - start < duration:
        check_stop()
        time.sleep(0.1)


# ---------------------------------------------------------------------------
# Core utility functions
# ---------------------------------------------------------------------------

def find_tesseract_path() -> str:
    """Attempts to find the Tesseract OCR executable on a Windows system."""
    import shutil
    tess_in_path = shutil.which("tesseract")
    if tess_in_path:
        return tess_in_path
    import getpass
    username = getpass.getuser()
    for path_template in DEFAULT_TESSERACT_PATHS:
        path_str = path_template.replace("{username}", username)
        path = Path(path_str)
        if path.exists():
            return str(path)
    return ""

def load_config() -> dict:
    """Loads configuration, validates keys, and injects defaults for missing values."""
    config = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                loaded = json.load(f)
                for k, v in loaded.items():
                    config[k] = v
            logger.info("Successfully loaded configuration from whatsapp_config.json")
        except Exception as e:
            logger.warning(f"Failed to read config file: {e}. Using defaults.")
    else:
        logger.info("Configuration file not found. Using default profile.")

    for k, v in DEFAULT_CONFIG.items():
        if k not in config:
            config[k] = v

    if not config.get("tesseract_cmd"):
        resolved_path = find_tesseract_path()
        if resolved_path:
            config["tesseract_cmd"] = resolved_path
            logger.info(f"Auto-resolved Tesseract path to: {resolved_path}")
        else:
            logger.warning("Could not auto-detect Tesseract OCR path. Tesseract must be in your PATH or configured manually.")
            config["tesseract_cmd"] = "tesseract"

    pytesseract.pytesseract.tesseract_cmd = config["tesseract_cmd"]
    return config

def save_config(config: dict):
    """Saves the configuration to whatsapp_config.json."""
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
        logger.info(f"Configuration saved to {CONFIG_FILE.resolve()}")
    except Exception as e:
        logger.error(f"Failed to save configuration: {e}")

def play_alert_sound(sound_file: str):
    """Plays a custom sound file if configured, otherwise plays a native winsound beep."""
    if sound_file and Path(sound_file).exists():
        try:
            logger.info(f"Playing alert sound: {sound_file}")
            winsound.PlaySound(sound_file, winsound.SND_FILENAME)
            return
        except Exception as e:
            logger.warning(f"winsound.PlaySound failed: {e}. Using beep fallback.")
    
    logger.info("Playing system beep alert...")
    for _ in range(3):
        winsound.Beep(1000, 500)
        time.sleep(0.1)

def force_click(x: int, y: int, hold_duration: float = 0.12):
    """Positions the cursor at (x, y), waits briefly for UI hover state to register, and executes a click."""
    pyautogui.moveTo(x, y)
    time.sleep(0.15)
    pyautogui.mouseDown()
    time.sleep(hold_duration)
    pyautogui.mouseUp()
    time.sleep(0.05)


# ---------------------------------------------------------------------------
# WhatsApp Window Management
# ---------------------------------------------------------------------------

def focus_whatsapp_main_window() -> bool:
    """Finds, maximizes, and activates the main WhatsApp chat window. Returns True if successful."""
    windows = gw.getWindowsWithTitle("WhatsApp")
    if not windows:
        logger.warning("No WhatsApp window found.")
        return False
    
    whatsapp_win = None
    for w in windows:
        if w.title == "WhatsApp":
            if w.width > w.height or w.width >= 1000:
                whatsapp_win = w
                break
    if not whatsapp_win:
        for w in windows:
            if w.title == "WhatsApp":
                whatsapp_win = w
                break
    if not whatsapp_win:
        whatsapp_win = windows[0]
        
    try:
        if whatsapp_win.isMinimized:
            whatsapp_win.restore()
        whatsapp_win.maximize()
        whatsapp_win.activate()
        time.sleep(0.5)
        logger.info(f"Focused WhatsApp window: '{whatsapp_win.title}'")
        return True
    except Exception as e:
        logger.error(f"Failed to focus WhatsApp window: {e}")
        return False

def get_whatsapp_call_window():
    """Finds active WhatsApp call window by orientation (height > width) and restores it if minimized."""
    try:
        windows = [w for w in gw.getWindowsWithTitle("WhatsApp") if w.title == "WhatsApp"]
        if not windows:
            return None
        if len(windows) == 1:
            w = windows[0]
            if w.width >= 1000 and w.width > w.height:
                return None
        for w in windows:
            is_minimized = w.isMinimized or w.left < -10000 or w.top < -10000
            if not is_minimized:
                is_portrait = w.height > w.width
                is_micro = w.width < 400 and w.height < 400
                if is_micro:
                    logger.info("WhatsApp call window is micro-minimized. Restoring...")
                    try:
                        w.restore()
                        w.activate()
                        time.sleep(1.0)
                    except Exception as err:
                        logger.error(f"Failed to restore micro-minimized window: {err}")
                    is_portrait = w.height > w.width
                # Relaxed bounds: orientation check plus minimum viable dimensions
                if is_portrait and w.width >= 200 and w.height >= 300:
                    return w
            else:
                logger.info("WhatsApp window is minimized. Verifying state...")
                try:
                    w.restore()
                    w.activate()
                    time.sleep(1.0)
                    if w.height > w.width and w.width >= 200 and w.height >= 300:
                        return w
                except Exception as restore_err:
                    logger.error(f"Failed to check minimized window: {restore_err}")
    except Exception as e:
        logger.error(f"Error searching for WhatsApp call window: {e}")
    return None


# ---------------------------------------------------------------------------
# Automated Contact Finder
# ---------------------------------------------------------------------------

def open_contact_chat(contact_name: str) -> bool:
    """Searches for a contact by name in WhatsApp using the search bar and opens their chat."""
    if not contact_name or not contact_name.strip():
        return True

    logger.info(f"Searching for contact: '{contact_name}'")

    if not focus_whatsapp_main_window():
        logger.error("Cannot search for contact: WhatsApp window not found.")
        return False

    time.sleep(0.5)

    pyautogui.hotkey("ctrl", "f")
    time.sleep(0.8)

    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.1)
    pyautogui.typewrite(contact_name, interval=0.05)
    time.sleep(1.5)

    windows = gw.getWindowsWithTitle("WhatsApp")
    whatsapp_win = None
    for w in windows:
        if w.title == "WhatsApp" and (w.width > w.height or w.width >= 1000):
            whatsapp_win = w
            break
    if not whatsapp_win and windows:
        whatsapp_win = windows[0]

    if not whatsapp_win:
        logger.error("Could not find WhatsApp window to click first search result.")
        return False

    # Click the first item in the sidebar list (x=230, y=330 relative to window top-left)
    click_x = whatsapp_win.left + 230
    click_y = whatsapp_win.top + 330
    logger.info(f"Clicking first search result in sidebar at: {click_x}, {click_y}")
    
    force_click(click_x, click_y, hold_duration=0.1)
    time.sleep(1.0)

    logger.info(f"Opened chat for contact: '{contact_name}'")
    return True


# ---------------------------------------------------------------------------
# OCR Engine (Non-intrusive, no focus stealing)
# ---------------------------------------------------------------------------

def preprocess_image(img_np: np.ndarray) -> np.ndarray:
    """Preprocesses a cropped screenshot to optimize OCR readability."""
    gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
    upscaled = cv2.resize(gray, (0, 0), fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    _, thresh = cv2.threshold(upscaled, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    n_white = np.sum(thresh == 255)
    n_black = np.sum(thresh == 0)
    if n_white < n_black:
        thresh = cv2.bitwise_not(thresh)
    return thresh

def perform_ocr(bbox: dict) -> str:
    """Screenshots the timer region silently and extracts text via PyTesseract without stealing focus."""
    call_win = get_whatsapp_call_window()
    if call_win:
        x = call_win.left + int((call_win.width - 120) / 2)
        y = call_win.top + int(call_win.height * 0.61)
        w = 120
        h = 40
    else:
        x, y, w, h = bbox["x"], bbox["y"], bbox["w"], bbox["h"]

    screenshot = pyautogui.screenshot(region=(x, y, w, h))
    img_np = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    processed = preprocess_image(img_np)
    custom_config = r"--psm 7 -c tessedit_char_whitelist=0123456789:"
    try:
        text = pytesseract.image_to_string(processed, config=custom_config)
        return text.strip()
    except pytesseract.TesseractNotFoundError:
        logger.error("Tesseract-OCR was not found. Please verify tesseract_cmd path in whatsapp_config.json")
        sys.exit(1)
    except Exception as e:
        logger.error(f"OCR Error: {e}")
        return ""


# ---------------------------------------------------------------------------
# Calibration & Dry-run
# ---------------------------------------------------------------------------

def wait_for_key_press(key_name="Enter", vk_code=0x0D):
    """Waits globally for a key press using ctypes on Windows."""
    while ctypes.windll.user32.GetAsyncKeyState(vk_code) & 0x8000:
        time.sleep(0.05)
    print(f"[Keyboard Hook] Waiting for you to press {key_name} on your keyboard...")
    while not (ctypes.windll.user32.GetAsyncKeyState(vk_code) & 0x8000):
        time.sleep(0.05)
    while ctypes.windll.user32.GetAsyncKeyState(vk_code) & 0x8000:
        time.sleep(0.05)
    time.sleep(0.1)

def calibrate_coordinates():
    """Interactive CLI to record coordinates for call buttons using global hotkeys."""
    print("\n" + "="*55)
    print("       WHATSAPP CALL BOT - CALIBRATION MODE       ")
    print("="*55)
    
    confirm_input = input("Does your WhatsApp require a confirmation/second click to start a call? [y/n] (default: n):\n> ").strip().lower()
    needs_confirm = (confirm_input == "y")

    print("\nThis mode records screen coordinates for clicks.")
    print("Hover your mouse over each item and press Enter.\n")

    config = load_config()

    step_num = 1

    print(f"{step_num}. Click on WhatsApp to bring it into focus, then press Enter.")
    wait_for_key_press("Enter", 0x0D)
    print("Calibration started!\n")
    step_num += 1

    print(f"{step_num}. Hover mouse over the VOICE CALL button (phone icon, top-right).")
    wait_for_key_press("Enter", 0x0D)
    x, y = pyautogui.position()
    config["call_button_1_coords"] = [x, y]
    print(f"   Captured Voice Call Button 1 at: {x}, {y}\n")
    step_num += 1

    if needs_confirm:
        print(f"{step_num}. Click the voice call button manually to open the confirmation screen.")
        print("   Hover mouse over the second/confirmation call button.")
        wait_for_key_press("Enter", 0x0D)
        x, y = pyautogui.position()
        config["call_button_2_coords"] = [x, y]
        print(f"   Captured Voice Call Button 2 at: {x}, {y}\n")
        step_num += 1
    else:
        config["call_button_2_coords"] = None

    print(f"{step_num}. Hover over the VIDEO CALL button (camera icon, top-right).")
    wait_for_key_press("Enter", 0x0D)
    x, y = pyautogui.position()
    config["video_call_button_1_coords"] = [x, y]
    print(f"   Captured Video Call Button 1 at: {x}, {y}\n")
    step_num += 1

    if needs_confirm:
        print(f"{step_num}. Click the video call button manually to open the confirmation screen.")
        print("   Hover mouse over the second/confirmation video call button.")
        wait_for_key_press("Enter", 0x0D)
        x, y = pyautogui.position()
        config["video_call_button_2_coords"] = [x, y]
        print(f"   Captured Video Call Button 2 at: {x}, {y}\n")
        step_num += 1
    else:
        config["video_call_button_2_coords"] = None

    save_config(config)
    print("Calibration complete! Coordinates saved.")
    print("You can verify OCR using: python whatsapp_call_bot.py --test-ocr")
    print("="*55 + "\n")

def test_ocr_dryrun():
    """Captures the bounding box region, saves debug images, and prints the OCR result."""
    config = load_config()
    print("\n" + "="*50)
    print("      WHATSAPP CALL BOT - OCR TESTING MODE      ")
    print("="*50)
    print("Make sure WhatsApp has an active call displaying the timer.")
    for i in range(10, 0, -1):
        print(f"Taking screenshot in {i} seconds... (Switch to WhatsApp call window now!)")
        time.sleep(1.0)
    print("Capturing now...")

    call_win = get_whatsapp_call_window()
    if call_win:
        x = call_win.left + int((call_win.width - 120) / 2)
        y = call_win.top + int(call_win.height * 0.61)
        w = 120
        h = 40
        print(f"Dynamically resolved Call Window: Left={call_win.left}, Top={call_win.top}, Width={call_win.width}, Height={call_win.height}")
    else:
        bbox = config["timer_bbox"]
        x, y, w, h = bbox["x"], bbox["y"], bbox["w"], bbox["h"]
        print("Using configuration file coordinates (Call window not found).")

    print(f"Screenshotting region: X={x}, Y={y}, W={w}, H={h}")
    screenshot = pyautogui.screenshot(region=(x, y, w, h))
    img_np = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    processed = preprocess_image(img_np)

    debug_raw_path = "debug_ocr_raw.png"
    debug_proc_path = "debug_ocr_processed.png"
    cv2.imwrite(debug_raw_path, img_np)
    cv2.imwrite(debug_proc_path, processed)
    print(f"\nRaw screenshot saved to: {Path(debug_raw_path).resolve()}")
    print(f"Preprocessed image saved to: {Path(debug_proc_path).resolve()}")

    custom_config = r"--psm 7 -c tessedit_char_whitelist=0123456789:"
    try:
        raw_text = pytesseract.image_to_string(processed, config=custom_config).strip()
        print(f"\nOCR Output (Whitelist): '{raw_text}'")
        raw_text_no_whitelist = pytesseract.image_to_string(processed, config="--psm 7").strip()
        print(f"OCR Output (Unrestricted): '{raw_text_no_whitelist}'")
        timer_pattern = re.compile(r"^0[0-5]:\d{2}$")
        is_match = bool(timer_pattern.match(raw_text))
        print(f"Regex Pattern Match (0[0-5]:\\d{{2}}): {is_match}")
    except pytesseract.TesseractNotFoundError:
        print("\nERROR: Tesseract OCR executable was not found.")
        print(f"Current setting: {config['tesseract_cmd']}")
    except Exception as e:
        print(f"\nError running OCR: {e}")
    print("="*50 + "\n")


# ---------------------------------------------------------------------------
# Dialing & Attempt State Handler
# ---------------------------------------------------------------------------

def dial_and_monitor_attempt(btn1_coords: list, btn2_coords: list, ring_timeout: float, timer_bbox: dict, end_call_coords: list) -> CallResult:
    """Executes a single dialing attempt and monitors call state. Returns a CallResult enum."""
    check_stop()

    # Safety: Focus WhatsApp main window once. Never click blindly if focus fails.
    if not focus_whatsapp_main_window():
        logger.error("Could not focus WhatsApp main window. Aborting click attempt safely.")
        return CallResult.WINDOW_FAILED

    # Click the call button(s)
    call_1_x, call_1_y = btn1_coords
    logger.info(f"Clicking Call Button 1 at: {call_1_x}, {call_1_y}")
    force_click(call_1_x, call_1_y, hold_duration=0.12)

    if btn2_coords:
        time.sleep(0.8)
        check_stop()
        call_2_x, call_2_y = btn2_coords
        logger.info(f"Clicking Call Button 2 at: {call_2_x}, {call_2_y}")
        force_click(call_2_x, call_2_y, hold_duration=0.12)

    # Separate UI initialization timeout (5.0s) from ring timeout
    logger.info("Waiting for WhatsApp call window to initialize...")
    start_wait = time.time()
    call_win_detected = False
    while time.time() - start_wait < 5.0:
        check_stop()
        if get_whatsapp_call_window() is not None:
            call_win_detected = True
            logger.info("WhatsApp Call window detected.")
            break
        interruptible_sleep(0.3)

    # Monitor dialing / ringing status for ring_timeout seconds
    logger.info(f"Monitoring call timer for {ring_timeout} seconds...")
    timer_pattern = re.compile(r"\d{1,2}:\d{2}")
    start_time = time.time()

    while time.time() - start_time < ring_timeout:
        check_stop()
        call_win = get_whatsapp_call_window()

        # Outcome 4: Unavailable / Busy / Declined
        # If call popup appeared and then closed rapidly before timer started
        if call_win_detected and call_win is None:
            logger.warning("Call popup closed before answer (recipient declined, busy, or line unavailable).")
            return CallResult.DECLINED_OR_UNAVAILABLE

        if call_win is not None:
            call_win_detected = True

        # Run non-intrusive OCR check
        ocr_text = perform_ocr(timer_bbox)
        match = timer_pattern.search(ocr_text)
        if match:
            detected_timer = match.group(0)
            logger.info(f"Call answered! Timer detected: '{detected_timer}'")
            return CallResult.ANSWERED

        interruptible_sleep(1.0)

    # Outcome 2: No Answer (Ring timeout reached without pick up)
    logger.warning(f"Call was not answered within {ring_timeout} seconds. Hanging up...")
    call_win = get_whatsapp_call_window()
    if call_win:
        end_x = call_win.left + int(call_win.width * 0.5)
        end_y = call_win.top + int(call_win.height * 0.88)
        logger.info(f"Clicking End Call button at: {end_x}, {end_y}")
        force_click(end_x, end_y, hold_duration=0.1)
        time.sleep(1.0)
        try:
            call_win.close()
        except Exception:
            pass
    else:
        end_x, end_y = end_call_coords
        logger.info(f"Clicking configured End Call at: {end_x}, {end_y}")
        force_click(end_x, end_y, hold_duration=0.1)

    return CallResult.NO_ANSWER


def monitor_active_call(sound_file: str, timer_bbox: dict):
    """Monitors an active answered call. Exits cleanly when the call finishes."""
    play_alert_sound(sound_file)
    logger.info("Monitoring active call... Will exit automatically when the call ends.")

    timer_pattern = re.compile(r"\d{1,2}:\d{2}")
    no_timer_count = 0

    while True:
        check_stop()
        interruptible_sleep(2.0)
        
        active_win = get_whatsapp_call_window()
        ocr_text = perform_ocr(timer_bbox)

        if timer_pattern.search(ocr_text):
            no_timer_count = 0  # Call is active
        else:
            no_timer_count += 1
            # Dual-Signal Termination: OCR missing for 8s AND window handle closed
            call_ended = (no_timer_count >= 4) or (active_win is None)
            if call_ended:
                logger.info("Active call has ended. Closing call window...")
                if active_win:
                    try:
                        active_win.close()
                    except Exception as e:
                        logger.error(f"Failed to close call window: {e}")
                else:
                    logger.info("Call window already closed.")
                sys.exit(0)


# ---------------------------------------------------------------------------
# Main Automation Loop
# ---------------------------------------------------------------------------

def run_automation():
    """Main execution loop to dial and monitor calls using the state machine."""
    start_esc_listener()
    logger.info("Press Esc at any time to stop the bot safely.")

    config = load_config()

    if config["call_button_1_coords"] == DEFAULT_CONFIG["call_button_1_coords"]:
        logger.warning("Coordinates are at default values. Run: python whatsapp_call_bot.py --calibrate")

    max_retries     = config.get("max_retries", 10)
    timeout_seconds = config.get("timeout_seconds", 25) # Ring timeout default: 25 seconds
    cooldown_min    = config.get("cooldown_min_seconds", 2.0)
    cooldown_max    = config.get("cooldown_max_seconds", 5.0)
    sound_file      = config.get("sound_file", "")
    
    # Interactive Prompts
    print("\n" + "="*55)
    print("            WHATSAPP CALL BOT SETUP            ")
    print("="*55)
    
    default_contact = config.get("contact_name", "").strip()
    contact_name_display = f"'{default_contact}'" if default_contact else "currently open chat"
    prompt_contact = input(f"1. Contact Name (Type name OR press Enter to use {contact_name_display}):\n> ").strip()
    contact_name = prompt_contact if prompt_contact else default_contact

    default_type = config.get("call_type", "voice").lower().strip()
    prompt_type = input(f"2. Call Type (Type 'voice' or 'video' OR press Enter for '{default_type}'):\n> ").strip().lower()
    call_type = prompt_type if prompt_type in ['voice', 'video'] else default_type
    
    print("="*55 + "\n")

    if call_type == "video":
        btn1_coords = config.get("video_call_button_1_coords", config["call_button_1_coords"])
        btn2_coords = config.get("video_call_button_2_coords", config["call_button_2_coords"])
        logger.info("Call type selected: VIDEO")
    else:
        btn1_coords = config["call_button_1_coords"]
        btn2_coords = config["call_button_2_coords"]
        logger.info("Call type selected: VOICE")

    logger.info("Starting WhatsApp Call Automation Bot.")
    logger.info(f"Parameters: max_retries={max_retries}, ring_timeout={timeout_seconds}s, cooldown={cooldown_min}-{cooldown_max}s")

    if contact_name:
        logger.info(f"Contact specified: '{contact_name}'. Opening chat...")
        if not open_contact_chat(contact_name):
            logger.error("Failed to open contact chat. Exiting.")
            sys.exit(1)
        logger.info("Chat opened. Starting call loop...")
        time.sleep(1.0)
    else:
        logger.info("No contact_name set in config. Assuming chat is already open.")

    for attempt in range(1, max_retries + 1):
        check_stop()
        logger.info(f"--- CALL ATTEMPT {attempt} / {max_retries} ---")

        result = dial_and_monitor_attempt(
            btn1_coords=btn1_coords,
            btn2_coords=btn2_coords,
            ring_timeout=timeout_seconds,
            timer_bbox=config["timer_bbox"],
            end_call_coords=config["end_call_coords"]
        )

        if result == CallResult.USER_CANCELLED:
            logger.info("Bot stopped by user (Esc key). Exiting.")
            sys.exit(0)

        elif result == CallResult.ANSWERED:
            logger.info("Call was successfully answered!")
            monitor_active_call(sound_file, config["timer_bbox"])
            sys.exit(0)

        elif result == CallResult.DECLINED_OR_UNAVAILABLE:
            logger.info("Call attempt was declined, busy, or line unavailable. Retrying after cooldown...")

        elif result == CallResult.NO_ANSWER:
            logger.info("Call reached ring timeout without answer. Retrying after cooldown...")

        elif result == CallResult.WINDOW_FAILED:
            logger.warning("WhatsApp window was unavailable. Retrying after cooldown...")

        # Cooldown period before next retry
        check_stop()
        cooldown = random.uniform(cooldown_min, cooldown_max)
        logger.info(f"Cooldown: {cooldown:.2f}s before next attempt...")
        interruptible_sleep(cooldown)

    logger.error(f"Reached max retry limit ({max_retries}) without answer. Exiting.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="WhatsApp Desktop Call Automation Bot",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Config options (set in whatsapp_config.json):\n"
            "  contact_name       : Name of the contact to search and call (leave empty to use open chat)\n"
            "  call_type          : 'voice' or 'video' (default: voice)\n"
            "  sound_file         : Path to a .wav file to play when call is answered\n"
            "  timeout_seconds    : Ring timeout seconds before hanging up (default: 25)\n"
            "  max_retries        : Maximum number of call attempts (default: 10)\n"
            "  cooldown_min/max   : Random cooldown range (seconds) between retries\n"
        )
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--calibrate", action="store_true", help="Interactively record screen coordinates for voice and video call buttons")
    group.add_argument("--test-ocr",  action="store_true", help="Perform a dry-run screenshot and OCR extraction of the call timer")
    group.add_argument("--run",       action="store_true", help="Run the call automation loop")

    args = parser.parse_args()

    if args.calibrate:
        calibrate_coordinates()
    elif args.test_ocr:
        test_ocr_dryrun()
    elif args.run:
        run_automation()

if __name__ == "__main__":
    pyautogui.FAILSAFE = False
    main()
