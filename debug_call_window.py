import sys
import time
from pathlib import Path

try:
    import pyautogui
    import cv2
    import pygetwindow as gw
    import numpy as np
except ImportError:
    print("Please activate your virtual environment: venv\\Scripts\\activate")
    sys.exit(1)

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
            is_minimized = w.isMinimized or w.left < -10000 or w.top < -10000
            
            if not is_minimized:
                is_portrait = w.height > w.width
                is_micro = w.width < 400 and w.height < 400
                
                if is_micro:
                    try:
                        w.restore()
                        w.activate()
                        time.sleep(1.0)
                    except Exception:
                        pass
                    is_portrait = w.height > w.width
                
                if is_portrait and 400 <= w.width <= 900 and 500 <= w.height <= 1000:
                    return w
            else:
                try:
                    w.restore()
                    w.activate()
                    time.sleep(1.0)
                    if w.height > w.width and 400 <= w.width <= 900 and 500 <= w.height <= 1000:
                        return w
                except Exception:
                    pass
    except Exception:
        pass
    return None

def main():
    print("="*60)
    print("            WHATSAPP WINDOW DIAGNOSTIC TOOL")
    print("="*60)
    # Countdown loop
    for i in range(10, 0, -1):
        print(f"Scanning in {i} seconds... (Switch to WhatsApp call window now!)")
        time.sleep(1.0)
    
    logical_w, logical_h = pyautogui.size()
    screenshot = pyautogui.screenshot()
    physical_w, physical_h = screenshot.size
    scale_factor = physical_w / logical_w
    
    print(f"Logical Screen Size: {logical_w}x{logical_h}")
    print(f"Physical Screen Size: {physical_w}x{physical_h}")
    print(f"DPI Scale Factor: {scale_factor:.2f}x (e.g., {int(scale_factor*100)}%)")
    
    call_win = get_whatsapp_call_window()
    if not call_win:
        print("\nCould not find active WhatsApp call window.")
        print("Please make sure the call window is open and not minimized.")
        print("All WhatsApp windows found:")
        for w in gw.getWindowsWithTitle("WhatsApp"):
            print(f"  Title: '{w.title}' | Pos: ({w.left}, {w.top}) | Size: {w.width}x{w.height}")
    else:
        print(f"\nFound Call Window:")
        print(f"  Logical Pos: ({call_win.left}, {call_win.top})")
        print(f"  Logical Size: {call_win.width}x{call_win.height}")
        
        # Calculate physical window coords
        phys_left = int(call_win.left * scale_factor)
        phys_top = int(call_win.top * scale_factor)
        phys_width = int(call_win.width * scale_factor)
        phys_height = int(call_win.height * scale_factor)
        
        print(f"  Physical Pos: ({phys_left}, {phys_top})")
        print(f"  Physical Size: {phys_width}x{phys_height}")
        
        # Crop the call window from the full screenshot and save it
        img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        call_crop = img[phys_top:phys_top+phys_height, phys_left:phys_left+phys_width]
        
        crop_path = "debug_call_window.png"
        cv2.imwrite(crop_path, call_crop)
        print(f"\nSaved call window screenshot to: {Path(crop_path).resolve()}")
        print("Please check this image. It should contain only the call window.")
        
    print("\n" + "="*60)

if __name__ == "__main__":
    main()
