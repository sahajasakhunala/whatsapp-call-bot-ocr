import re
import sys
import time
from pathlib import Path

try:
    import pyautogui
    import cv2
    import pytesseract
    import numpy as np
except ImportError:
    print("Please activate your virtual environment first: venv\\Scripts\\activate")
    sys.exit(1)

# Set Tesseract path from config
CONFIG_FILE = Path("whatsapp_config.json")
tesseract_cmd = "tesseract"
if CONFIG_FILE.exists():
    try:
        import json
        with open(CONFIG_FILE, "r") as f:
            cfg = json.load(f)
            if cfg.get("tesseract_cmd"):
                tesseract_cmd = cfg["tesseract_cmd"]
    except Exception:
        pass

pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

def main():
    print("="*60)
    print("        WHATSAPP CALL TIMER COORDINATE DETECTOR")
    print("="*60)
    print("Make sure the WhatsApp call is active on your screen showing the timer.")
    print("Starting full-screen scan in 5 seconds...")
    
    for i in range(5, 0, -1):
        print(f"Scanning in {i} seconds...")
        time.sleep(1.0)
        
    print("\nScanning screen... Please wait...")
    try:
        screenshot = pyautogui.screenshot()
        img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        
        # We also convert to grayscale for better OCR on the full screen
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Use image_to_data to get word-by-word locations
        data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)
        
        timer_pattern = re.compile(r"^\d{1,2}:\d{2}$")
        matches = []
        
        for i in range(len(data['text'])):
            text = data['text'][i].strip()
            # Clean up common OCR noise
            text_clean = text.replace('o', '0').replace('O', '0').replace('I', '1').replace('l', '1')
            if timer_pattern.match(text) or timer_pattern.match(text_clean):
                x = data['left'][i]
                y = data['top'][i]
                w = data['width'][i]
                h = data['height'][i]
                matches.append((text, x, y, w, h))
                
        if not matches:
            print("\nCould not find any timer patterns on screen.")
            print("Try running the script again, making sure the WhatsApp window is in the foreground and not blocked.")
        else:
            print(f"\nSuccess! Found {len(matches)} potential timer region(s):")
            for idx, (txt, x, y, w, h) in enumerate(matches, 1):
                # Add a small padding (e.g. 5-10 pixels) around the detected box for stability
                pad_x = max(0, x - 5)
                pad_y = max(0, y - 3)
                pad_w = w + 10
                pad_h = h + 6
                print(f"\nMatch {idx}: '{txt}'")
                print(f"  Coordinates: X={x}, Y={y}, W={w}, H={h}")
                print(f"  Recommended Config values (with padding):")
                print(f"    \"x\": {pad_x}")
                print(f"    \"y\": {pad_y}")
                print(f"    \"w\": {pad_w}")
                print(f"    \"h\": {pad_h}")
                
    except pytesseract.TesseractNotFoundError:
        print("\nError: Tesseract OCR was not found. Please ensure it is installed and path is configured.")
    except Exception as e:
        print(f"\nAn error occurred: {e}")
    print("\n" + "="*60)

if __name__ == "__main__":
    main()
