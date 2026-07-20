import time
import json
import sys
from pathlib import Path

try:
    import pyautogui
    import cv2
    import pytesseract
    import numpy as np
except ImportError:
    print("Please activate your virtual environment: venv\\Scripts\\activate")
    sys.exit(1)

CONFIG_FILE = Path("whatsapp_config.json")

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_config(config: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)
    print(f"Configuration saved to {CONFIG_FILE.resolve()}")

def preprocess_image(img_np: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
    upscaled = cv2.resize(gray, (0, 0), fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    _, thresh = cv2.threshold(upscaled, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    n_white = np.sum(thresh == 255)
    n_black = np.sum(thresh == 0)
    if n_white < n_black:
        thresh = cv2.bitwise_not(thresh)
    return thresh

def main():
    print("="*60)
    print("            WHATSAPP TIMER CALIBRATION UTILITY")
    print("="*60)
    print("This utility will record the coordinates of the WhatsApp call timer.")
    print("You will hover your mouse cursor over the corners of the timer text.")
    print("Make sure the WhatsApp call is active on screen before starting.\n")
    
    input("Press Enter in this terminal window when you are ready to start...")
    
    config = load_config()
    
    # Step 1: Top-Left Corner
    for i in range(5, 0, -1):
        print(f"Hover mouse over the TOP-LEFT corner of the timer text... {i}")
        time.sleep(1.0)
    x1, y1 = pyautogui.position()
    print(f"--> Captured Top-Left: X={x1}, Y={y1}\n")
    
    # Step 2: Bottom-Right Corner
    for i in range(5, 0, -1):
        print(f"Hover mouse over the BOTTOM-RIGHT corner of the timer text... {i}")
        time.sleep(1.0)
    x2, y2 = pyautogui.position()
    print(f"--> Captured Bottom-Right: X={x2}, Y={y2}\n")
    
    w = max(10, x2 - x1)
    h = max(10, y2 - y1)
    
    config["timer_bbox"] = {
        "x": x1,
        "y": y1,
        "w": w,
        "h": h
    }
    save_config(config)
    print(f"\nSaved Timer Bounding Box: X={x1}, Y={y1}, W={w}, H={h}")
    
    # Step 3: Run immediate OCR verification
    print("\nRunning test OCR scan on this region...")
    try:
        # Load Tesseract CMD from config
        if config.get("tesseract_cmd"):
            pytesseract.pytesseract.tesseract_cmd = config["tesseract_cmd"]
            
        screenshot = pyautogui.screenshot(region=(x1, y1, w, h))
        img_np = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        processed = preprocess_image(img_np)
        
        cv2.imwrite("debug_ocr_raw.png", img_np)
        cv2.imwrite("debug_ocr_processed.png", processed)
        
        custom_config = r"--psm 7 -c tessedit_char_whitelist=0123456789:"
        text = pytesseract.image_to_string(processed, config=custom_config).strip()
        
        print(f"\nOCR Output: '{text}'")
        if text:
            print("OCR read the text successfully!")
        else:
            print("OCR read empty text. Please check the debug image files in this folder to verify they are cropped correctly.")
            
    except Exception as e:
        print(f"Error testing OCR: {e}")
        
    print("\n" + "="*60)

if __name__ == "__main__":
    main()
