# WhatsApp Desktop Call Automation System

A production-grade Python automation system designed to manage dialing, connection detection, active call monitoring, and lifecycle management on WhatsApp Desktop for Windows. 

The system leverages computer vision, dynamic window classification, and Optical Character Recognition (OCR) to deliver reliable automated calling workflows without requiring Administrator process elevation.

---

## Key Features

- **Automated Dialing & Contact Selection**: Automatically searches for a contact by name (`Ctrl+F`), selects the contact from the sidebar results, and initiates Voice or Video calls.
- **OCR Timer Connection Detection**: Uses PyTesseract and OpenCV preprocessing (grayscale, cubic upscaling, Otsu binarization, and inversion) to detect call duration timers (e.g., `00:01`) directly from screen screenshots.
- **Orientation-Based Window Classifier**: Uses geometric aspect ratios to distinguish between landscape main chat windows and portrait active call popups. Restores micro-minimized call popups automatically.
- **4-State Call Outcome Classification**: Distinguishes between Answered Calls, Unanswered Calls (No Answer), Missed/User Cancelled Calls, and Unavailable/Busy/Declined calls.
- **Active Call Lifecycle Monitoring**: Monitors ongoing calls and automatically closes the call popup and terminates the bot when the conversation finishes (detected via 8-second timer absence).
- **Asynchronous Global Emergency Stop**: Features a background daemon thread polling `Esc` (`VK_ESCAPE`) to allow immediate, non-blocking termination at any time without needing terminal window focus.

---

## Technology Stack

- **Language**: Python 3.x
- **Automation & Window Control**: PyAutoGUI, PyGetWindow
- **Computer Vision & OCR**: OpenCV (`cv2`), PyTesseract, Pillow (`PIL`), NumPy
- **Win32 System Integration**: `ctypes` (Win32 APIs)
- **Pattern Matching**: Regular Expressions (`re`)

---

## Prerequisites

1. **WhatsApp Desktop**: Official WhatsApp Desktop application installed and logged in on Windows.
2. **Tesseract-OCR**: Google's Tesseract OCR engine installed on Windows.
   - [Download Installer](https://github.com/UB-Mannheim/tesseract/wiki)
   - Installation path: `C:\Program Files\Tesseract-OCR\tesseract.exe`

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
   pip install -r requirements.txt
   ```

---

## Usage Guide

### 1. Calibration
Run the interactive calibration mode to record button screen coordinates:
```bash
python whatsapp_call_bot.py --calibrate
```
Follow the interactive prompt:
- Specify whether your WhatsApp version requires a confirmation pop-up click.
- Hover over the Voice and Video call buttons and press **Enter** to record their positions.

### 2. Testing OCR Region Extraction
Verify OCR timer detection accuracy while a call is active:
```bash
python whatsapp_call_bot.py --test-ocr
```
The utility saves `debug_ocr_raw.png` and `debug_ocr_processed.png` locally and prints the extracted timer text.

### 3. Running the Automation Bot
Execute the main automation loop:
```bash
python whatsapp_call_bot.py --run
```
Follow the startup prompts:
1. Enter contact name to search and open their chat (or press **Enter** to use currently open chat).
2. Select call type (`voice` or `video`).

Press **Esc** at any time to stop the bot immediately.

---

## Project Structure

- `whatsapp_call_bot.py`: Main automation system containing window management, contact search, hover-aware clicking, OCR engine, call monitoring, and CLI interface.
- `docs/user-manual.md`: Comprehensive user manual documenting calibration, OCR verification, execution prompts, emergency controls, and troubleshooting.
- `docs/engineering-iterations.md`: Detailed engineering log documenting the development evolution, trade-offs, failed experiments, and architectural postmortems.
- `debug_call_window.py`: Diagnostic utility for verifying window bounds and DPI scaling factors.
- `find_timer.py`: Diagnostic utility for locating timer coordinates across the display.
- `requirements.txt`: Project package dependencies list.
- `whatsapp_config.json`: Local settings containing custom click coordinates and user preferences (generated during calibration).

---

## License & Disclaimer
This project is developed for educational and automation demonstration purposes. Use responsibly in compliance with relevant terms of service.
