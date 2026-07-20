# WhatsApp Desktop Call Automation Bot

An automated Python script designed to handle calling workflows on the WhatsApp Desktop application for Windows. It utilizes GUI automation, image processing, and Optical Recognition (OCR) to initiate calls, detect when the recipient answers, monitor the call duration, and automatically close the call window once the conversation ends.

---

## Features

- **Automated Dialing**: Automates the multi-step click sequence required to place a call in WhatsApp Desktop.
- **Live Connection Detection (OCR)**: Uses Tesseract OCR and OpenCV image processing (upscaling, binarization, and inversion) to read the active call timer (e.g., `00:01`) directly from the screen.
- **Resilient Focus Management**: Detects if the WhatsApp call window is minimized or micro-minimized (WhatsApp's Picture-in-Picture mode) and automatically restores and focuses it to keep the timer visible.
- **Smart Hang-up Detection**: Detects if you or the recipient manually ends the call, terminating the script cleanly.
- **Auto-Cleanup**: Monitors active calls and automatically closes the call window via OS commands when the call finishes.
- **Failed Call Retries**: If a call is rejected, busy, offline, or goes unanswered, the bot automatically hangs up, waits for a randomized cooldown period (to prevent spam detection), and retries.

---

## Technology Stack

- **Python 3**
- **PyAutoGUI**: For controlling mouse movements and clicks.
- **PyGetWindow**: For locating and managing the state of WhatsApp Desktop windows.
- **OpenCV (cv2) & NumPy**: For image preprocessing (enhancing contrast and resizing) to optimize OCR accuracy.
- **PyTesseract**: An interface for Google's Tesseract-OCR engine to read digits from the screen.

---

## Prerequisites

1. **WhatsApp Desktop**: Make sure the official WhatsApp Desktop application is installed and logged in on Windows.
2. **Tesseract-OCR**: Install Google's Tesseract OCR engine on Windows.
   - [Download Installer](https://github.com/UB-Mannheim/tesseract/wiki)
   - Note down the installation path (typically `C:\Program Files\Tesseract-OCR\tesseract.exe`).

---

## Installation & Setup

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/sahajasakhunala/whatsapp-call-bot-ocr.git
   cd whatsapp-call-bot-ocr
   ```

2. **Set up Virtual Environment**:
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```

3. **Install Dependencies**:
   ```bash
   pip install pyautogui opencv-python numpy pytesseract pygetwindow
   ```

---

## Calibration & Usage

Before running the bot, you need to calibrate it to match your screen layout and resolution.

### Step 1: Calibrate Click Coordinates
Open the chat of the contact you want to call, maximize WhatsApp Desktop, and run:
```bash
python whatsapp_call_bot.py --calibrate
```
Follow the interactive CLI instructions:
- Hover your mouse over the top-right Call icon and press **Enter**.
- Wait for the popup to show, hover your mouse over the green **Voice call** button, and press **Enter**.

This creates a local `whatsapp_config.json` file storing your screen coordinates.

### Step 2: Test OCR Bounding Box
Start a manual call. Once the call timer appears, run:
```bash
python whatsapp_call_bot.py --test-ocr
```
The script will capture the timer region and print the OCR output. Verify that the output correctly matches the timer digits (e.g., `00:04`).

### Step 3: Run the Bot
Open the target contact's chat, maximize WhatsApp, and run:
```bash
python whatsapp_call_bot.py --run
```
The bot will take over to click, dial, monitor, alert you upon connection, and clean up the call window when done.

---

## Project Structure

- `whatsapp_call_bot.py`: The main automation script containing calibration, OCR detection, active monitoring, and dialing loops.
- `debug_call_window.py`: A diagnostic tool to verify the screen coordinates and dimensions of open WhatsApp windows.
- `find_timer.py`: A helper utility to scan the screen for specific call timers.
- `whatsapp_config.json`: Local settings containing custom click coordinates and timeouts (automatically created during calibration).
- `.gitignore`: Excludes local configurations, debug screenshots, and virtual environments from commits.

---

## Disclaimer
This project is for educational and automation demonstration purposes. Be mindful of rate-limiting policies and use responsibly to avoid spamming contacts.
