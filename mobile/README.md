# Jarvis 24/7 Buddy — Mobile App (1-Click PWA & Standalone Android APK)

Jarvis connects to your **Python FastAPI Backend + Native PostgreSQL 16 Server** while caching your entire schedule, Fixed Weekly Routine, and Proof-of-Wake alarms locally in `IndexedDB` and `localStorage` so your phone keeps working even when internet drops completely.

---

## Option 1: 1-Click Mobile App Install (Recommended — Zero Build Tools Required)

1. Start your Jarvis Python backend on your PC or Cloud VPS:
   ```powershell
   py -3.11 setup_postgres.py
   py -3.11 -m jarvis.main web
   ```
2. Open the Jarvis dashboard on your computer and click **📲 Install Mobile App**, or open `http://<YOUR-LAN-OR-VPS-IP>:8000` in **Chrome** (Android) or **Safari** (iOS) on your phone.
3. Tap **Install Mobile AppNow (1-Click)** or choose **Add to Home Screen** from the browser menu.
4. Once installed, Jarvis runs full-screen, caches `/api/sync` locally, runs the 5-second due-reminder watchdog, and fires the 15-second repeating **"Anas, wake up!"** voice loop offline.

---

## Option 2: Build the Native Android `.apk` (`.\build_apk.ps1`)

This folder (`mobile/`) is a complete **Capacitor JS** mobile project (`com.anas.jarvis`) that packages the offline-first dashboard and `mobile-bridge.js` into a standalone Android `.apk`.

### Prerequisites
- **Node.js 18+** (`npm` available in PATH)
- **JDK 17+** and **Android SDK** (or Android Studio) for compiling the Gradle APK

### 1-Command APK Build
From PowerShell inside `c:\projects\jarvis\mobile\`:

```powershell
.\build_apk.ps1
```

Or via npm scripts:
```powershell
npm install
npm run sync
npm run build:apk
```

### What `.\build_apk.ps1` Does
1. Copies the latest `static/` assets into `mobile/www/` while preserving the mobile entry UI (`mobile/www/index.html` and `mobile/www/mobile-bridge.js`).
2. Runs `npm install` to install `@capacitor/core`, `@capacitor/cli`, `@capacitor/android`, and `@capacitor/local-notifications`.
3. Runs `npx cap sync android` to sync `www/` into the native Android container.
4. Runs `.\android\gradlew.bat assembleDebug` to output **`mobile/app-debug.apk`** (and `mobile/android/app/build/outputs/apk/debug/app-debug.apk`).

### Connecting the APK to Your Python + Native PostgreSQL Server
1. Install `app-debug.apk` on your Android phone.
2. At the top of the app, enter your **Python Backend Server URL** (e.g., `http://192.168.1.100:8000` on Wi-Fi LAN or your Cloud VPS URL) and tap **Save & Sync**.
3. Whenever online, `mobile-bridge.js` automatically syncs `/api/sync` into local `IndexedDB` and `localStorage`. When offline, the dashboard, 5-second reminder watchdog, and 15-second repeating `"Anas, wake up!"` voice alarm loop continue operating seamlessly from local storage.
