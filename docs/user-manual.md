# User Manual and Operating Guide

This document provides a detailed operational guide for configuring, calibrating, running, and customizing the WhatsApp Desktop Call Automation System on Windows.

---

## 1. System Requirements & Installation

### Requirements
- **Operating System**: Windows 10 or Windows 11 (64-bit).
- **Application**: Official WhatsApp Desktop application installed and logged in.
- **OCR Engine**: Google Tesseract-OCR installed on the host machine.
  - Standard Installation Path: `C:\Program Files\Tesseract-OCR\tesseract.exe`
  - Download: [Tesseract-OCR Windows Installer](https://github.com/UB-Mannheim/tesseract/wiki)

### Environment Setup
1. Clone the repository and navigate into the root directory:
   ```cmd
   git clone https://github.com/sahajasakhunala/whatsapp-call-bot-ocr.git
   cd whatsapp-call-bot-ocr
   ```
2. Create and activate a Python virtual environment:
   ```cmd
   python -m venv venv
   venv\Scripts\activate
   ```
3. Install required package dependencies:
   ```cmd
   pip install -r requirements.txt
   ```

---

## 2. Calibration Mode (`--calibrate`)

Calibration records your display coordinates for WhatsApp call buttons and configures whether your application layout requires a confirmation pop-up click.

### Execution
Run the calibration command in your terminal:
```cmd
python whatsapp_call_bot.py --calibrate
```

### Calibration Workflow
1. **Confirmation Pop-Up Inquiry**:
   The terminal will prompt:
   `Does your WhatsApp require a confirmation/second click to start a call? [y/n]`
   - Type `y` if clicking the top-right call icon opens a second green "Voice call" dialog in the middle of the screen.
   - Press `Enter` (default `n`) if clicking the top-right call icon dials immediately.

2. **Step-by-Step Coordinate Capture**:
   - **Step 1 (Focus)**: Click on the WhatsApp window to bring it into focus, then press `Enter` in the terminal.
   - **Step 2 (Voice Call Icon)**: Hover your mouse over the top-right phone receiver icon and press `Enter`.
   - **Step 3 (Confirmation Button)** *(if enabled)*: Hover over the green confirmation button and press `Enter`.
   - **Step 4 (Video Call Icon)**: Hover over the top-right camera icon and press `Enter`.

Coordinates are automatically saved to `whatsapp_config.json`.

---

## 3. OCR Testing & Verification (`--test-ocr`)

Before running automated dialing, verify that Tesseract OCR accurately extracts timer digits from your active call window.

### Execution
1. Manually start a WhatsApp call so the active call popup displaying the timer (e.g. `00:05`) is on screen.
2. Run the test command:
   ```cmd
   python whatsapp_call_bot.py --test-ocr
   ```

### Output Validation
The script will capture the timer region, process the image, and save two diagnostic images in the root directory:
- `debug_ocr_raw.png`: The raw cropped screenshot.
- `debug_ocr_processed.png`: The upscaled, binarized, and inverted image passed to Tesseract.

Verify in the terminal that `OCR Output (Whitelist)` matches the active timer on screen.

---

## 4. Automated Execution (`--run`)

### Launching the Bot
Start the automation loop:
```cmd
python whatsapp_call_bot.py --run
```

### Startup Interactive Prompts
1. **Contact Name**:
   `1. Contact Name (Type name OR press Enter to use currently open chat):`
   - Type a contact name (e.g., `John Doe`) to have the bot automatically search (`Ctrl+F`), select, verify, and open their chat pane.
   - Press `Enter` to dial whichever chat is currently focused on screen.

2. **Call Type Selection**:
   `2. Call Type (Type 'voice' or 'video' OR press Enter for 'voice'):`
   - Type `video` to initiate a video call using saved video coordinates.
   - Press `Enter` for a standard voice call.

### Execution Cycle
- The bot searches for the target contact and verifies the chat header.
- It clicks the configured call buttons to dial.
- It monitors for call pickup using PyTesseract OCR.
- If unanswered after the ring timeout (default: 25 seconds), it hangs up, waits for a randomized cooldown period (default: 2-5 seconds), and retries.
- When answered, it plays an alert sound, monitors the ongoing call, closes the popup when finished, and exits cleanly.

---

## 5. Emergency Stop & Safety Features

### Global Hotkey Termination (`Esc`)
Press **`Esc`** on your keyboard at any time during execution.
- The background daemon listener detects `VK_ESCAPE` asynchronously.
- The bot stops execution instantly (within 100ms) without needing command terminal focus.

### Window Focus Safety
The bot verifies that WhatsApp Desktop is focused before dispatching mouse clicks. If WhatsApp cannot be focused, execution halts safely (`WINDOW_FAILED`) to prevent accidental clicks on other applications.

---

## 6. Configuration Reference (`whatsapp_config.json`)

You can edit `whatsapp_config.json` directly to customize system parameters:

```json
{
    "call_button_1_coords": [1740, 84],
    "call_button_2_coords": null,
    "video_call_button_1_coords": [1676, 87],
    "video_call_button_2_coords": null,
    "end_call_coords": [1217, 858],
    "timer_bbox": {
        "x": 900,
        "y": 630,
        "w": 120,
        "h": 40
    },
    "timeout_seconds": 25,
    "max_retries": 10,
    "cooldown_min_seconds": 2.0,
    "cooldown_max_seconds": 5.0,
    "tesseract_cmd": "C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
    "sound_file": "alert.wav",
    "call_type": "voice",
    "contact_name": "John Doe"
}
```

### Parameter Key
- `timeout_seconds`: Ring timeout duration in seconds before attempting hang-up (default: `25`).
- `max_retries`: Maximum number of consecutive dial attempts (default: `10`).
- `cooldown_min_seconds` / `cooldown_max_seconds`: Range for randomized pause between retries.
- `sound_file`: Path to a `.wav` file to play when a call connects (leave empty for system beep).
- `tesseract_cmd`: Absolute path to the Tesseract executable.

---

## 7. Troubleshooting Guide

| Issue | Root Cause | Solution |
|---|---|---|
| `TesseractNotFoundError` | Tesseract is not installed or path is incorrect. | Install Tesseract and set `tesseract_cmd` path in `whatsapp_config.json`. |
| Clicks land in wrong area | Window size or screen resolution changed. | Re-run `python whatsapp_call_bot.py --calibrate` to update coordinates. |
| Bot sits on confirmation popup | Second click confirmation is required but disabled. | Re-run `--calibrate` and answer `y` to confirmation prompt. |
| Chat verification fails | Search query text does not match contact header. | Type full contact name accurately at the startup prompt. |
