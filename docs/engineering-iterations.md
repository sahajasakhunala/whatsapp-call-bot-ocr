# Engineering Iterations

## Purpose

This document records the major engineering decisions made during the development of the WhatsApp Desktop Call Automation System. It focuses on the reasoning behind architectural changes, unsuccessful experiments, technical constraints, and the solutions that were ultimately adopted.

Rather than documenting every code change, this file captures the evolution of the system and the lessons learned throughout development.

## Project Goal

Develop a reliable Windows automation bot that repeatedly calls a selected WhatsApp Desktop contact until they answer.

The bot is designed to:
- Search for a contact automatically.
- Initiate Voice or Video calls.
- Retry automatically while calls remain unanswered.
- Detect when the recipient answers using OCR.
- Stop calling immediately after an answered call.
- Monitor active calls and detect when the call ends.
- Close the WhatsApp call window automatically and exit cleanly.

## Tech Stack

- Python 3.x
- PyAutoGUI, PyGetWindow, Keyboard
- OpenCV, PyTesseract, Pillow, NumPy
- ctypes (Win32 API)
- Regular Expressions (re)

## System Architecture

```
Search Contact
      |
      v
  Open Chat
      |
      v
  Start Call
      |
      v
Monitor Call Window
      |
      v
 OCR Timer Detection
      |
      +-------------------+
      |                   |
      v                   v
   Answered          Not Answered
      |                   |
      |                   v
      |            Detect Call End
      |                   |
      |                   v
      |               Retry Call
      |
      v
Stop Retry Loop
      |
Play Alert Sound
      |
Monitor Active Call
      |
Detect Call End
      |
Close Call Window
      |
 Exit Bot
```

## Engineering Approach

Every major decision came from real testing and root-cause analysis rather than assumptions. The design prioritizes Windows-native tools, UI-state timing, and clean error handling.

---

## 1. Direct Click Automation using PyAutoGUI

Status: Replaced

### Problem
The initial prototype clicked fixed screen coordinates using PyAutoGUI.

### Approach
Call `pyautogui.click()` using recorded screen coordinates.

### Observations
Static coordinates failed as soon as the WhatsApp window moved or resized. PyAutoGUI's default failsafe also crashed the script (`FailSafeException`) if the mouse accidentally hit a screen corner (`0, 0`). In addition, physical mouse movement during execution dragged the cursor off-target.

### Decision
Disable PyAutoGUI failsafe boundaries and calculate coordinates dynamically from the application window handle.

---

## 2. Window Detection and Orientation Classifier

Status: Adopted

### Problem
`pygetwindow` returned multiple windows matching `"WhatsApp"` (chat window, call window, browser tabs, script files), causing clicks to land on the wrong window.

### Approach
Differentiate windows using aspect ratio and dimensions.

### Observations
WhatsApp Desktop opens a separate window for active calls with different dimensions than the main chat window:
- Main Chat Window: Landscape (`width > height` and `width >= 1000px`).
- Call Popup: Portrait (`height > width`, usually `400px` to `900px` wide).
- Micro-Minimized Call Window: Windows smaller than `400px x 400px` or off-screen coordinates are restored using `.restore()` and `.activate()`.

### Decision
Filter window handles by aspect ratio to target the active call window reliably.

---

## 3. OCR Pipeline for Timer Detection

Status: Adopted

### Problem
The bot needed to detect when a call transitioned from ringing to answered by reading the timer (e.g. `00:01`).

### Approach
Screenshot the timer region and pass it to Tesseract OCR.

### Observations
Raw Tesseract failed on native WhatsApp screenshots. The dark blurred background and white text provided too little contrast, returning empty strings or random characters.

### Decision
Added an OpenCV preprocessing pipeline before calling OCR:
1. Convert to grayscale.
2. Upscale image 4x using cubic interpolation.
3. Apply Otsu thresholding.
4. Automatically invert colors if the background is dark, giving Tesseract dark text on a pure white background.
5. Pass to Tesseract using single-line mode (`--psm 7`) and a character whitelist (`0123456789:`).
Regular expressions parse formats like `0:03`, `1:42`, or `01:23:45`.

---

## 4. Dynamic Timer Bounding Box

Status: Adopted

### Problem
Hardcoded timer screen coordinates broke whenever the call window moved.

### Approach
Calculate the timer screenshot region relative to the active call window.

### Observations
Using relative offsets keeps the screenshot region centered over the timer regardless of window position:
- `x = left + int((width - 120) / 2)`
- `y = top + int(height * 0.61)`
- `w = 120, h = 40`

### Decision
Calculate OCR crop boundaries dynamically from the call window rectangle.

---

## 5. Win32 BlockInput API

Status: Rejected

### Problem
Prevent the user's mouse from moving the cursor away during a click.

### Approach
Call Win32 `BlockInput(True)` before clicking and `BlockInput(False)` after.

### Observations
`BlockInput` returned `0` (failure). Under Windows User Interface Privilege Isolation (UIPI), non-elevated scripts cannot block hardware input. It silently fails unless run as Administrator.

### Decision
Rejected requiring Administrator rights to keep setup simple and safe.

---

## 6. Low-Level Mouse Hooks (WH_MOUSE_LL)

Status: Rejected

### Problem
Intercept physical mouse movement at the driver level without needing Administrator rights.

### Approach
Install a global `WH_MOUSE_LL` hook using `SetWindowsHookExW` with a Win32 message loop in a background thread.

### Observations
Running a Windows message loop inside a Python thread created synchronization issues. If the thread hung, mouse input was trapped globally, freezing the mouse for the entire system until a force reboot.

### Decision
Abandoned mouse hooks due to system stability risks.

---

## 7. Win32 ClipCursor API

Status: Rejected

### Problem
Confine mouse movement to a 1x1 pixel box over the target button.

### Approach
Call `ClipCursor` with a tiny rectangle during the click.

### Observations
Windows automatically clears `ClipCursor` bounds as soon as the foreground window changes. Because the script must focus WhatsApp before clicking, focus switching instantly removed the cursor trap.

### Decision
Abandoned hardware cursor locking.

---

## 8. High-Frequency SetCursorPos Thread

Status: Rejected

### Problem
Keep pulling the cursor back to the target button faster than the mouse can move away.

### Approach
Run a background thread calling `SetCursorPos` in a zero-sleep loop.

### Observations
The loop maxed out CPU usage. Fast mouse movements still injected position updates between thread ticks, causing mouse jitter and missed clicks.

### Decision
Dropped all mouse-locking attempts. Focused instead on timing clicks to match application UI states.

---

## 9. Hover-Aware Click Engine

Status: Adopted

### Problem
Instant `SetCursorPos` teleportation followed by raw Win32 mouse clicks moved the mouse to the button, but WhatsApp ignored the click.

### Approach
Investigated how the UI handles mouse events.

### Observations
WhatsApp Desktop is an Electron / React Native app. Web-based desktop UIs handle DOM events asynchronously. Teleporting the cursor and clicking in less than a millisecond fires `mousedown` before the DOM engine registers the hover (`mouseenter`) state, so the click listener ignores it.

### Decision
Move the cursor with `pyautogui.moveTo()`, wait `150ms` for the hover state to register, then trigger `mouseDown()` and `mouseUp()`. Click reliability reached 100%.

---

## 10. Multi-Version UI Adaptation

Status: Adopted

### Problem
Different WhatsApp Desktop versions behave differently: some require a second confirmation click after pressing call, while others dial immediately.

### Approach
Make confirmation clicks and call types configurable during calibration.

### Observations
Asking the user during `--calibrate` if a second click is needed allows setting second-stage coordinates to `None`. The script skips the second click automatically when not required, supporting both single-click and two-step dialing, as well as voice and video call switching.

### Decision
Adopted optional second-click calibration and dynamic call type selection.

---

## 11. Call Outcome Classification

Status: Adopted

### Problem
Treating all failed attempts the same made it impossible to handle different call end states properly.

### Approach
Categorize calls into four distinct outcomes:

1. **Answered Call**
   - Indicator: Timer continuously counts up (`0:01`, `0:02`).
   - Action: Stop dialing, play sound, monitor active call, wait until finished, close window, exit.

2. **No Answer**
   - Indicator: Timer never appears after `timeout_seconds`.
   - Action: Click end call, close window, wait for cooldown, retry.

3. **Missed / User Cancelled**
   - Indicator: Call window closed manually before answer.
   - Action: Detect closed window handle and exit cleanly.

4. **Unavailable / Busy / Declined**
   - Indicator: Call window closes quickly without showing a timer (line busy or call rejected).
   - Action: Detect rapid window closure, wait for cooldown, retry automatically.

### Decision
Adopted four-state outcome handling for deterministic call management.

---

## 12. Active Call Monitoring and Auto Teardown

Status: Adopted

### Problem
The bot needs to keep running while the call is ongoing and exit only when the conversation finishes.

### Approach
Add a post-answer monitoring loop that checks if the call is active.

### Observations
- Pressing `Esc` anywhere triggers an asynchronous background listener (`GetAsyncKeyState`), allowing instant emergency stop without needing terminal focus.
- Once answered, the bot checks the timer every 2 seconds. If no timer is detected for 8 consecutive seconds (4 consecutive reads), the call has ended. The bot closes the call popup (`active_win.close()`) and exits cleanly (`sys.exit(0)`).

### Decision
Adopted background `Esc` key stopping and 8-second timer absence monitoring for auto-teardown.

---

# Key Takeaways

- High-level automation libraries are simple but can be unpredictable.
- Native Win32 APIs offer control, but OS security rules must be respected.
- OCR accuracy comes down to good image preprocessing.
- Electron apps need time to register hover states before accepting clicks.
- Robust automation works with application behavior rather than fighting OS protections.

---

# System Components

| Component | Choice |
|---|---|
| Window Detection | PyGetWindow with aspect-ratio filter |
| Click Execution | PyAutoGUI with 150ms hover delay |
| Image Processing | OpenCV grayscale, 4x cubic upscale, Otsu threshold, inversion |
| OCR Reading | PyTesseract in single-line mode with digit whitelist |
| Timer Match | Regex pattern matching |
| Target Region | Relative percentage coordinates from window frame |
| Outcome Tracking | Four-state classifier (Answered, No Answer, Missed, Unavailable) |
| Emergency Stop | Win32 Esc key listener thread |
| Call Teardown | Active monitoring with 8-second missing timer check |
