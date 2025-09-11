# Kronos Thermo v8

**Kronos Thermo** is a lightweight background service add-on for **Kodi 21 (Omega)** on **LibreELEC / Raspberry Pi**. 
It continuously monitors the system temperature and protects your device against overheating.

## 🔥 Hot Features

- **Boot delay (configurable in code)** 
  Waits for Kodi to fully load before monitoring begins (default: 33s).

- **Temperature thresholds** 
  - ⚠️ **85 °C** → One-time warning notification. 
  - ⛔ **95 °C** → Playback is force-stopped, and a critical notification is shown. 
    (Prevents thermal runaway while the Pi firmware throttles.)

- **Debounce & cooldown** 
  - No notification spam: warnings only reset once cooled. 
  - Critical stop notifications have a cooldown (default: 11s).

- **Custom icons** 
  - Icons can be placed in `resources/media/` (e.g., `warn.png`, `stop.png`) and are shown in notifications.

- **Abort-safe service loop** 
  - Uses `xbmc.Monitor.waitForAbort()` instead of blocking sleeps. 
  - Clean exit when Kodi shuts down.
