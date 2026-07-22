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
    logger.error("Please install dependencies: pip install pyautogui opencv-python pytesseract numpy pygetwindow playsound==1.2.2")
    sys.exit(1)

# playsound has a history of platform issues; import defensively
HAS_PLAYSOUND = False
try:
    import playsound
    HAS_PLAYSOUND = True
except ImportError:
    logger.warning("playsound library is not installed or failed to import. Falling back to winsound.")

# Default configuration parameters
CONFIG_FILE = Path("whatsapp_config.json")
DEFAULT_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    r"C:\Users\{username}\AppData\Local\Programs\Tesseract-OCR\tesseract.exe",
    r"C:\Users\{username}\AppData\Local\Tesseract-OCR\tesseract.exe"
]

DEFAULT_CONFIG = {
    "call_button_1_coords": [1000, 100],  # Default placeholders, must calibrate
    "call_button_2_coords": [1000, 150],  # Default placeholders, must calibrate
    "end_call_coords": [960, 800],      # Default placeholders, must calibrate
    "timer_bbox": {
        "x": 920,
        "y": 750,
        "w": 80,
        "h": 30
    },
    "timeout_seconds": 20,
    "max_retries": 10,
    "cooldown_min_seconds": 2.0,
    "cooldown_max_seconds": 5.0,
    "tesseract_cmd": "",
    "sound_file": ""
}

# ---------------------------------------------------------------------------
# Win32 RECT structure for ClipCursor API
# ---------------------------------------------------------------------------
class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def find_tesseract_path() -> str:
    """Attempts to find the Tesseract OCR executable on a Windows system."""
    # Check if 'tesseract' is in system PATH
    import shutil
    tess_in_path = shutil.which("tesseract")
    if tess_in_path:
        return tess_in_path

    # Check common installation locations
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
                # Merge loaded config, ensuring we preserve default fields
                for k, v in loaded.items():
                    if k in config:
                        config[k] = v
            logger.info("Successfully loaded configuration from whatsapp_config.json")
        except Exception as e:
            logger.warning(f"Failed to read config file: {e}. Using defaults.")
    else:
        logger.info("Configuration file not found. Using default profile.")

    # Auto-resolve Tesseract path if not explicitly configured
    if not config.get("tesseract_cmd"):
        resolved_path = find_tesseract_path()
        if resolved_path:
            config["tesseract_cmd"] = resolved_path
            logger.info(f"Auto-resolved Tesseract path to: {resolved_path}")
        else:
            logger.warning("Could not auto-detect Tesseract OCR path. Tesseract must be in your PATH or configured manually.")
            config["tesseract_cmd"] = "tesseract"

    # Configure pytesseract path
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
    """Plays an alert sound using playsound, falling back to winsound."""
    if sound_file and Path(sound_file).exists() and HAS_PLAYSOUND:
        try:
            logger.info(f"Playing alert sound from file: {sound_file}")
            playsound.playsound(sound_file)
            return
        except Exception as e:
            logger.warning(f"playsound failed to play sound file: {e}. Falling back to winsound.")
    
    # Winsound fallback
    logger.info("Playing fallback system sound alert...")
    for _ in range(3):
        winsound.Beep(1000, 500)  # 1000Hz frequency, 500ms duration
        time.sleep(0.1)

def force_click(x: int, y: int, hold_duration: float = 0.12):
    """Positions the cursor at (x, y) via Win32 SetCursorPos and executes a hardware-level left click."""
    user32 = ctypes.windll.user32
    ix, iy = int(x), int(y)

    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004

    user32.SetCursorPos(ix, iy)
    time.sleep(0.02)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(hold_duration)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.02)

def focus_whatsapp_window() -> bool:
    """Finds, maximizes, and activates the WhatsApp window. Returns True if successful."""
    windows = gw.getWindowsWithTitle("WhatsApp")
    if not windows:
        logger.warning("No window containing 'WhatsApp' in the title was found.")
        return False
    
    # Filter for the exact title to avoid matching browser tabs or scripts
    whatsapp_win = None
    for w in windows:
        if w.title == "WhatsApp":
            whatsapp_win = w
            break
            
    if not whatsapp_win:
        whatsapp_win = windows[0]
        
    try:
        # Restore if minimized
        if whatsapp_win.isMinimized:
            whatsapp_win.restore()
        # Maximize to ensure coordinates are consistent
        whatsapp_win.maximize()
        whatsapp_win.activate()
        time.sleep(0.5)
        logger.info(f"Focused and maximized WhatsApp window: '{whatsapp_win.title}'")
        return True
    except Exception as e:
        logger.error(f"Failed to focus WhatsApp window: {e}")
        return False

def wait_for_key_press(key_name="Enter", vk_code=0x0D):
    """Waits globally for a key press (even when out of focus) using ctypes on Windows."""
    import ctypes
    # Clear any previous pressed state
    while ctypes.windll.user32.GetAsyncKeyState(vk_code) & 0x8000:
        time.sleep(0.05)
    print(f"[Keyboard Hook] Waiting for you to press {key_name} on your keyboard...")
    # Wait for key down
    while not (ctypes.windll.user32.GetAsyncKeyState(vk_code) & 0x8000):
        time.sleep(0.05)
    # Wait for key up
    while ctypes.windll.user32.GetAsyncKeyState(vk_code) & 0x8000:
        time.sleep(0.05)
    # A short sleep to prevent accidental bounce
    time.sleep(0.1)

def calibrate_coordinates():
    """Interactive CLI to record coordinates for the two call buttons using global hotkeys."""
    print("\n" + "="*50)
    print("      WHATSAPP CALL BOT - CALIBRATION MODE      ")
    print("="*50)
    print("This mode records screen coordinates for clicks.")
    print("Instructions: Hover your mouse cursor over the specified item,")
    print("then press Enter on your keyboard (globally, no need to focus this window).\n")

    config = load_config()

    # Step 0: Focus Warmup Press (throwaway click/press)
    print("0. Prep Step: Click on your WhatsApp window to bring it to focus.")
    print("   Once WhatsApp is visible and focused, press Enter on your keyboard to start.")
    wait_for_key_press("Enter", 0x0D)
    print("Calibration sequence started!\n")

    # Step 1: Call Button 1
    print("1. Hover mouse over the first Call Button on WhatsApp.")
    wait_for_key_press("Enter", 0x0D)
    x, y = pyautogui.position()
    config["call_button_1_coords"] = [x, y]
    print(f"Captured Call Button 1 at: {x}, {y}\n")

    # Step 2: Call Button 2 (Call again / confirmation)
    print("2. Click that Call Button manually so the next Call screen/button becomes visible.")
    print("   Hover mouse over the second Call button (Call again / Confirmation).")
    wait_for_key_press("Enter", 0x0D)
    x, y = pyautogui.position()
    config["call_button_2_coords"] = [x, y]
    print(f"Captured Call Button 2 at: {x}, {y}\n")

    # Save
    save_config(config)
    print("Calibration completed successfully!")
    print("You can verify the OCR text using the --test-ocr command.")
    print("="*50 + "\n")

def preprocess_image(img_np: np.ndarray) -> np.ndarray:
    """Preprocesses a cropped screenshot to optimize OCR readability."""
    # Convert PIL/RGB to Grayscale
    gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
    
    # Upscale 4x using Cubic Interpolation (makes small text larger and cleaner)
    upscaled = cv2.resize(gray, (0, 0), fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    
    # Binarization using Otsu's thresholding
    _, thresh = cv2.threshold(upscaled, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    
    # Ensure text is black and background is white
    # Count black pixels vs white pixels. Usually background dominates.
    # In standard OCR, white background (255) is optimal.
    # If there are more black pixels (background is dark), we invert the image.
    n_white = np.sum(thresh == 255)
    n_black = np.sum(thresh == 0)
    if n_white < n_black:
        thresh = cv2.bitwise_not(thresh)
        
    return thresh

def get_whatsapp_call_window():
    """Finds the active WhatsApp call window based on title and orientation (portrait), and restores it if minimized/micro-minimized."""
    try:
        windows = [w for w in gw.getWindowsWithTitle("WhatsApp") if w.title == "WhatsApp"]
        if not windows:
            return None
            
        # If there is only one "WhatsApp" window and it's landscape, it's the main chat window (no call active)
        if len(windows) == 1:
            w = windows[0]
            if w.width >= 1000 and w.width > w.height:
                return None
                
        for w in windows:
            # The call window is portrait (height > width), main window is landscape (width > height)
            # Minimize state window dimensions can be small/zero, so check coordinates too
            is_minimized = w.isMinimized or w.left < -10000 or w.top < -10000
            
            # If not minimized, we can check dimensions immediately
            if not is_minimized:
                is_portrait = w.height > w.width
                is_micro = w.width < 400 and w.height < 400
                
                # If it's a micro-minimized call window, restore it
                if is_micro:
                    logger.info("WhatsApp call window is micro-minimized. Restoring it to screen...")
                    try:
                        w.restore()
                        w.activate()
                        time.sleep(1.0)
                    except Exception as err:
                        logger.error(f"Failed to restore micro-minimized window: {err}")
                    is_portrait = w.height > w.width
                
                if is_portrait and 400 <= w.width <= 900 and 500 <= w.height <= 1000:
                    return w
            else:
                # If minimized, to avoid restoring the main chat window by mistake:
                # We check if this is likely the call window (the main chat window has a larger restored size,
                # but if we are unsure, we restore and verify it is indeed portrait).
                # Since the main window is typically large, we only restore if it's the secondary window or small.
                logger.info("WhatsApp window is minimized. Verifying state...")
                try:
                    w.restore()
                    w.activate()
                    time.sleep(1.0)
                    if w.height > w.width and 400 <= w.width <= 900 and 500 <= w.height <= 1000:
                        return w
                except Exception as restore_err:
                    logger.error(f"Failed to check minimized window: {restore_err}")
    except Exception as e:
        logger.error(f"Error searching for WhatsApp call window: {e}")
    return None

def perform_ocr(bbox: dict) -> str:
    """Screenshots the timer region, processes it, and extracts text via PyTesseract."""
    call_win = get_whatsapp_call_window()
    if call_win:
        try:
            # Force focus to bring the call window to the foreground
            call_win.activate()
            time.sleep(0.2)
        except Exception:
            pass
        # The call timer is centered horizontally and sits at roughly 61% down the call window height
        x = call_win.left + int((call_win.width - 120) / 2)
        y = call_win.top + int(call_win.height * 0.61)
        w = 120
        h = 40
    else:
        x, y, w, h = bbox["x"], bbox["y"], bbox["w"], bbox["h"]
    
    # Take screenshot of the region
    screenshot = pyautogui.screenshot(region=(x, y, w, h))
    
    # Convert screenshot to OpenCV format (numpy array)
    img_np = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    
    # Preprocess
    processed = preprocess_image(img_np)
    
    # Run Tesseract with specific config:
    # PSM 7: Treat the image as a single text line.
    # Whitelist digits and colon.
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

def test_ocr_dryrun():
    """Captures the bounding box region, saves debug images, and prints the OCR result."""
    config = load_config()
    
    print("\n" + "="*50)
    print("      WHATSAPP CALL BOT - OCR TESTING MODE      ")
    print("="*50)
    print("Please make sure WhatsApp has an active call displaying the timer on screen.")
    
    # Automatic countdown to give user time to focus the WhatsApp call window
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

    # Capture
    screenshot = pyautogui.screenshot(region=(x, y, w, h))
    img_np = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    processed = preprocess_image(img_np)
    
    # Save debug files locally
    debug_raw_path = "debug_ocr_raw.png"
    debug_proc_path = "debug_ocr_processed.png"
    cv2.imwrite(debug_raw_path, img_np)
    cv2.imwrite(debug_proc_path, processed)
    
    print(f"\nRaw screenshot saved to: {Path(debug_raw_path).resolve()}")
    print(f"Preprocessed image saved to: {Path(debug_proc_path).resolve()}")
    
    # Run Tesseract
    custom_config = r"--psm 7 -c tessedit_char_whitelist=0123456789:"
    try:
        raw_text = pytesseract.image_to_string(processed, config=custom_config).strip()
        print(f"\nOCR Output (Whitelist): '{raw_text}'")
        
        # Test without whitelist for comparison
        raw_text_no_whitelist = pytesseract.image_to_string(processed, config="--psm 7").strip()
        print(f"OCR Output (Unrestricted): '{raw_text_no_whitelist}'")
        
        # Regex Match Check
        timer_pattern = re.compile(r"^0[0-5]:\d{2}$")
        is_match = bool(timer_pattern.match(raw_text))
        print(f"Regex Pattern Match (0[0-5]:\\d{{2}}): {is_match}")
        
    except pytesseract.TesseractNotFoundError:
        print("\nERROR: Tesseract OCR executable was not found.")
        print(f"Current setting: {config['tesseract_cmd']}")
        print("Please check your installation and ensure it matches the path in whatsapp_config.json")
    except Exception as e:
        print(f"\nError running OCR: {e}")
    print("="*50 + "\n")

def run_automation():
    """Main execution loop to dial and monitor calls."""
    config = load_config()
    
    # Validate coordinate configs
    # We do a basic validation check. If all values are placeholders, warn the user.
    if config["call_button_1_coords"] == DEFAULT_CONFIG["call_button_1_coords"]:
        logger.warning("Coordinates are at default values. You likely need to run: python whatsapp_call_bot.py --calibrate")

    max_retries = config.get("max_retries", 10)
    timeout_seconds = config.get("timeout_seconds", 20)
    cooldown_min = config.get("cooldown_min_seconds", 2.0)
    cooldown_max = config.get("cooldown_max_seconds", 5.0)
    
    # Match standard timer formats like 00:01 or 0:01
    timer_pattern = re.compile(r"\d{1,2}:\d{2}")
    
    logger.info("Starting WhatsApp Call Automation Bot.")
    logger.info(f"Parameters: max_retries={max_retries}, call_timeout={timeout_seconds}s, cooldown range={cooldown_min}-{cooldown_max}s")

    for attempt in range(1, max_retries + 1):
        logger.info(f"--- CALL ATTEMPT {attempt} / {max_retries} ---")
        
        # 1. Focus the WhatsApp window
        if not focus_whatsapp_window():
            logger.warning("Could not focus WhatsApp. Clicking coordinates blindly...")
        
        # 2. Forcefully take mouse controls and click Call Buttons
        focus_whatsapp_window()
        
        call_1_x, call_1_y = config["call_button_1_coords"]
        logger.info(f"Clicking Call Button 1 at: {call_1_x}, {call_1_y}")
        force_click(call_1_x, call_1_y, hold_duration=0.12)
        time.sleep(0.8)
        
        call_2_x, call_2_y = config["call_button_2_coords"]
        logger.info(f"Clicking Call Button 2 at: {call_2_x}, {call_2_y}")
        force_click(call_2_x, call_2_y, hold_duration=0.12)
            
        # Wait up to 3 seconds for WhatsApp call window animation to complete
        logger.info("Waiting for WhatsApp call window to initialize...")
        start_wait = time.time()
        while time.time() - start_wait < 3.0:
            if get_whatsapp_call_window() is not None:
                break
            time.sleep(0.3)

        # 3. Monitor for timer
        logger.info(f"Monitoring call timer region for {timeout_seconds} seconds...")
        call_answered = False
        start_time = time.time()

            
        # Track if the call window has appeared during this attempt
        window_appeared = False
        if get_whatsapp_call_window() is not None:
            window_appeared = True
            logger.info("WhatsApp Call window detected.")
            
        while time.time() - start_time < timeout_seconds:
            call_win = get_whatsapp_call_window()
            
            # If the window appeared and is now gone, the user or recipient hung up
            if window_appeared and call_win is None:
                logger.info("Call window was closed. Stopping attempt and exiting.")
                sys.exit(0)
            
            if call_win is not None:
                window_appeared = True
                
            ocr_text = perform_ocr(config["timer_bbox"])
            
            # Search for timer pattern
            match = timer_pattern.search(ocr_text)
            if match:
                detected_timer = match.group(0)
                logger.info(f"Success! Detected call timer: '{detected_timer}' (OCR text was '{ocr_text}')")
                call_answered = True
                break
                
            time.sleep(1.0)  # Scan every 1 second
            
        if call_answered:
            logger.info("Call was successfully answered!")
            play_alert_sound(config["sound_file"])
            
            # Keep monitoring the active call until it ends, then close the window
            logger.info("Monitoring active call... Will automatically close the window when the call ends.")
            no_timer_count = 0
            while True:
                time.sleep(2.0)
                active_win = get_whatsapp_call_window()
                
                ocr_text = perform_ocr(config["timer_bbox"])
                if timer_pattern.search(ocr_text):
                    no_timer_count = 0  # Call is active
                else:
                    no_timer_count += 1
                    # If no timer is seen for 4 checks (8 seconds), the call has ended
                    if no_timer_count >= 4:
                        logger.info("No active call timer detected for 8 seconds. Call has ended. Closing window...")
                        if active_win:
                            try:
                                active_win.close()
                            except Exception as e:
                                logger.error(f"Failed to close call window: {e}")
                        else:
                            logger.info("Call window handle not found. Exiting script.")
                        sys.exit(0)
            sys.exit(0)
            
        logger.warning(f"Call was not answered within {timeout_seconds} seconds. Hanging up...")
        call_win = get_whatsapp_call_window()
        if call_win:
            # Dynamically calculate the center of the hang-up button relative to window size
            end_x = call_win.left + int(call_win.width * 0.5)
            end_y = call_win.top + int(call_win.height * 0.88)
            logger.info(f"Clicking dynamic End Call button at: {end_x}, {end_y} (Window size: {call_win.width}x{call_win.height})")
            force_click(end_x, end_y, hold_duration=0.1)
            time.sleep(1.0)
            # Try to close the window as well since call was unanswered
            try:
                call_win.close()
            except Exception:
                pass
        else:
            end_x, end_y = config["end_call_coords"]
            logger.info(f"Clicking configured End Call button at: {end_x}, {end_y}")
            force_click(end_x, end_y, hold_duration=0.1)
        
        # Cooldown interval (randomized to prevent spam detection/rate limiting)
        cooldown = random.uniform(cooldown_min, cooldown_max)
        logger.info(f"Waiting for randomized cooldown of {cooldown:.2f} seconds before retrying...")
        time.sleep(cooldown)
        
    logger.error(f"Failed to connect call after reaching maximum retry limit ({max_retries}). Exiting.")
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="WhatsApp Desktop Screen Call Automation & OCR Bot")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--calibrate", action="store_true", help="Interactively record screen coordinates")
    group.add_argument("--test-ocr", action="store_true", help="Perform a dry-run screenshot and OCR extraction")
    group.add_argument("--run", action="store_true", help="Run the call automation loop")
    
    args = parser.parse_args()
    
    if args.calibrate:
        calibrate_coordinates()
    elif args.test_ocr:  # argparse maps --test-ocr to args.test_ocr
        test_ocr_dryrun()
    elif args.run:
        run_automation()

if __name__ == "__main__":
    # Disable PyAutoGUI failsafe entirely so user mouse movements to corners don't crash the script
    pyautogui.FAILSAFE = False
    main()
