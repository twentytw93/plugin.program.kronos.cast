#twentytw93-KronosTeam
from http.server import BaseHTTPRequestHandler, HTTPServer
import xbmc
import xbmcaddon
import xbmcgui
import urllib.parse
import threading
import json
import os
import cgi
import base64
import shutil
import time


ADDON = xbmcaddon.Addon()

server = None
_server_lock = threading.Lock()
_current_port = None 

CAST_IN_FLIGHT = False
CAST_TS = 0.0

def is_busy_or_progress_visible():
    """
    True if Kodi Busy/Progress is on-screen.
    Hard preflight blocker to avoid Kodi 21 SIGABRT on re-entrancy.
    """
    checks = (
        "Window.IsActive(busydialog)",
        "Window.IsActive(progressdialog)",
        "Window.IsActive(busydialognocancel)",
        "Window.IsActive(progressdialogbusy)",
    )
    try:
        return any(xbmc.getCondVisibility(c) for c in checks)
    except Exception:
        # Fail-safe: if query fails, assume busy to avoid crash
        return True

def _read_port():
    try:
        s = (ADDON.getSetting("port") or "").strip()   # string path is most reliable
        digits = "".join(ch for ch in s if ch.isdigit())
        p = int(digits) if digits else 9798
    except Exception:
        p = 9798
    if p < 1024 or p > 65535:
        p = 9798
    xbmc.log(f"[KronosCast] _read_port -> '{s}' => {p}", xbmc.LOGINFO)
    return p

def get_current_port():
    try:
        if server:
            return int(server.server_address[1])
    except Exception:
        pass
    return int(_current_port) if _current_port is not None else _read_port()

if os.name == 'nt':
    _home = os.getenv("USERPROFILE") or os.path.expanduser("~") or r"C:\Users\Public"
    MUSIC_DIR   = os.path.join(_home, "Music")
    VIDEO_DIR   = os.path.join(_home, "Videos")
    TORRENT_DIR = os.path.join(_home, "Torrents")
else:
    MUSIC_DIR   = "/storage/music"
    VIDEO_DIR   = "/storage/videos"
    TORRENT_DIR = "/storage/torrents"
    
for directory in (MUSIC_DIR, VIDEO_DIR, TORRENT_DIR):
    try:
        os.makedirs(directory, exist_ok=True)
    except Exception as e:
        xbmc.log(f"[KronosCast] mkdir failed for {directory}: {e}", xbmc.LOGWARNING)

def is_system_dialog_active():
    dialog_ids = [
        "Window.IsActive(busydialog)",
        "Window.IsActive(dialogerror)",
        "Window.IsActive(DialogConfirm.xml)",
        "Window.IsActive(DialogOK.xml)",
        "Window.IsActive(DialogYesNo.xml)"
    ]
    return any(xbmc.getCondVisibility(dialog) for dialog in dialog_ids)

def show_notification(title, message, is_error=False):
    icon = xbmcgui.NOTIFICATION_ERROR if is_error else xbmcgui.NOTIFICATION_INFO
    xbmcgui.Dialog().notification(title, message, icon, 3000)

def safe_play(url, media_type="video"):
    """
    Returns a tuple: (status, reason)
      - ("ok", None)              → dispatch attempted
      - ("blocked", "busy")       → busy/progress preflight hit
      - ("blocked", "duplicate")  → debounce hit (within 5s)
      - ("error", "exception")    → unexpected failure
    """
    try:
        # --- Preflight: block if Busy/Progress dialog is visible (prevents Kodi 21 SIGABRT) ---
        if is_busy_or_progress_visible():
            xbmc.log("[KronosCast] Cast blocked: busy/progress dialog visible", xbmc.LOGINFO)
            show_notification("[B]Kronos Cast[/B]", "Cast blocked: Busy/Progress dialog is active.", is_error=True)
            return ("blocked", "busy")

        # --- Debounce: drop duplicate casts within 5 seconds ---
        global CAST_IN_FLIGHT, CAST_TS
        now = time.time()
        if CAST_IN_FLIGHT and (now - CAST_TS) < 5.0:
            xbmc.log(f"[KronosCast] Cast ignored: duplicate within {now - CAST_TS:.2f}s", xbmc.LOGINFO)
            show_notification("[B]Kronos Cast[/B]", "Cast ignored: duplicate within 5s.", is_error=False)
            return ("blocked", "duplicate")

        CAST_IN_FLIGHT = True
        CAST_TS = now
        try:
            msg = "Casting your Video..." if media_type == "video" else "Playing your Audio..."
            custom_icon = os.path.join(ADDON.getAddonInfo('path'), "resources", "media", "cast_icon.png")
            xbmcgui.Dialog().notification("[B]Kronos Cast[/B]", msg, custom_icon, 3000)

            if url.startswith("plugin://plugin.video.youtube"):
                if not xbmc.getCondVisibility("System.HasAddon(plugin.video.youtube)"):
                    show_notification("[B]Kronos Cast[/B]", "YouTube Add-on Not Installed", is_error=True)
                    return ("error", "youtube_missing")
                # Stable path (RunPlugin) – JSON-RPC removed due to failures
                xbmc.executebuiltin(f'RunPlugin("{url}")')
                return ("ok", None)
            else:
                if url.startswith("/storage") and not os.path.exists(url):
                    show_notification("[B]Kronos Cast[/B]", "File Not Found", is_error=True)
                    return ("error", "file_not_found")
                xbmc.Player().play(url)
                return ("ok", None)
        finally:
            # Always clear in-flight so the next cast can proceed
            CAST_IN_FLIGHT = False

    except Exception as e:
        xbmc.log(f"[KronosCast] Playback failed: {str(e)}", xbmc.LOGERROR)
        show_notification("[B]Kronos Cast[/B]", "Playback Failed", is_error=True)
        return ("error", "exception")

def play_with_elementum(uri, is_torrent=False, allow_blocked=True):
    try:
        if is_torrent:
            torrent_path = os.path.join(TORRENT_DIR, "temp_cast.torrent")
            with open(torrent_path, 'wb') as f:
                if uri.startswith('data:'):
                    f.write(base64.b64decode(uri.split(',')[1]))
                else:
                    with open(uri, 'rb') as src:
                        f.write(src.read())
            uri = torrent_path

        if is_system_dialog_active() and not allow_blocked:
            xbmc.log("[KronosCast] Playback blocked due to active system dialog", xbmc.LOGINFO)
            show_notification("[B]Kronos Cast[/B]", "Uploading Blocked - Due to Active System Dialog", is_error=True)
            return

        elementum_url = f"plugin://plugin.video.elementum/play?uri={urllib.parse.quote(uri)}"
        xbmc.executebuiltin(f'PlayMedia("{elementum_url}")')
        show_notification("[B]Kronos Cast[/B]", "Sending to Elementum...")
    except Exception as e:
        xbmc.log(f"[KronosCast] Elementum error: {str(e)}", xbmc.LOGERROR)
        show_notification("[B]Kronos Cast[/B]", "Elementum not Available", is_error=True)

class RequestHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        try:
            xbmc.log("[KronosCast] " + (fmt % args), xbmc.LOGDEBUG)
        except Exception:
            pass

    def _ok(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

    def _json(self, data, code=200):
        self.send_response(code)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_GET(self):
        path_raw = self.path
        path = path_raw.lower()
        parsed = urllib.parse.urlparse(path_raw)
        query = urllib.parse.parse_qs(parsed.query)
        xbmc.log(f"[KronosCast] HTTP Request: {path}", xbmc.LOGINFO)

        try:
            if path.startswith("/cast"):
                url = query.get("url", [""])[0]

                # Stricter Busy/Progress guard
                if is_busy_or_progress_visible():
                    xbmc.log("[KronosCast] /cast blocked: busy/progress dialog visible", xbmc.LOGINFO)
                    show_notification("[B]Kronos Cast[/B]",
                                      "Cast blocked: Busy/Progress dialog is active.",
                                      is_error=True)
                    self._json({"status": "blocked", "reason": "busy"}, 423)
                    return

                # Block if a system dialog is up
                if is_system_dialog_active():
                    show_notification("[B]Kronos Cast[/B]",
                                      "Uploading Blocked - Due to Active System Dialog",
                                      is_error=True)
                    self._json({"status": "blocked", "reason": "system_dialog"}, 423)
                    return

                if xbmc.Player().isPlayingAudio():
                    show_notification("[B]Kronos Cast[/B]",
                                      "Uploading Blocked. Audio Player Is Active.",
                                      is_error=True)
                    self._json({"status": "blocked", "reason": "audio_active"}, 423)
                    return

                is_elementum = url.startswith("magnet:?") or query.get("torrent", [""])[0] == "true"

                if is_elementum:
                    play_with_elementum(url)
                    self._json({"status": "ok"})
                    return
                else:
                    media_type = "audio" if any(ext in url.lower() for ext in ['.mp3', '.wav', '.flac']) else "video"

                    # YouTube URL → hand off to YouTube plugin
                    if "youtube.com/watch" in url or "youtu.be" in url:
                        if "youtu.be/" in url:
                            vid = url.split("youtu.be/")[1].split("?")[0]
                        elif "v=" in url:
                            vid = url.split("v=")[1].split("&")[0]
                        url = f"plugin://plugin.video.youtube/play/?video_id={vid}"

                    status, reason = safe_play(url, media_type)

                    if status == "ok":
                        self._json({"status": "ok"})
                    elif status == "blocked":
                        self._json({"status": "blocked", "reason": reason}, 423)
                    else:
                        self._json({"status": "error", "reason": reason or "unknown"}, 500)
                    return

            elif path == "/play":
                xbmc.executebuiltin("PlayerControl(Play)")
                self._ok()
                return
            elif path == "/stop":
                xbmc.executebuiltin("PlayerControl(Stop)")
                self._ok()
                return
            elif path == "/mute":
                xbmc.executebuiltin("Action(Mute)")
                self._ok()
                return
            elif path == "/volup":
                xbmc.executebuiltin("Action(VolumeUp)")
                self._ok()
                return
            elif path == "/voldown":
                xbmc.executebuiltin("Action(VolumeDown)")
                self._ok()
                return
            elif path == "/shutdown":
                xbmc.executebuiltin("ShutDown()")
                self._ok()
                return

            elif path == "/clear":
                try:
                    for dir_path in [MUSIC_DIR, VIDEO_DIR, TORRENT_DIR]:
                        for filename in os.listdir(dir_path):
                            file_path = os.path.join(dir_path, filename)
                            try:
                                if os.path.isfile(file_path):
                                    os.remove(file_path)
                                elif os.path.isdir(file_path):
                                    shutil.rmtree(file_path)
                            except Exception as e:
                                xbmc.log(f"[KronosCast] Failed to delete {file_path}: {str(e)}", xbmc.LOGWARNING)
                    self._ok()
                except Exception as e:
                    xbmc.log(f"[KronosCast] Clear failed: {str(e)}", xbmc.LOGERROR)
                    self.send_error(500, "Clear failed")
                return

            elif path.startswith("/nowplaying"):
                now_playing_info = {"title": "", "time": "", "total": ""}
                try:
                    json_data = json.loads(xbmc.executeJSONRPC(
                        '{"jsonrpc":"2.0","method":"Player.GetItem","params":{"playerid":1,"properties":["label"]},"id":1}'
                    ))
                    now_playing_info["title"] = json_data.get("result", {}).get("item", {}).get("label", "")
                    player = xbmc.Player()
                    now_playing_info["time"] = str(int(player.getTime()))
                    now_playing_info["total"] = str(int(player.getTotalTime()))
                except Exception:
                    pass
                self._json(now_playing_info)
                return

            elif path.startswith("/browse"):
                media_type = query.get("type", ["music"])[0]
                folder = MUSIC_DIR if media_type == "music" else VIDEO_DIR
                try:
                    files = [
                        os.path.join(folder, f) for f in os.listdir(folder)
                        if f.lower().endswith((".mp4", ".mp3", ".mkv"))
                    ]
                except Exception:
                    files = []
                self._json(files)
                return

            elif path == "/":
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                html_path = os.path.join(ADDON.getAddonInfo('path'), "resources", "interface.html")
                try:
                    with open(html_path, "rb") as file:
                        self.wfile.write(file.read())
                except Exception:
                    self.wfile.write(b"<html><body><h1>Kronos Cast</h1></body></html>")
                return

            elif path.endswith(".png"):
                image_path = os.path.join(ADDON.getAddonInfo('path'), "resources", os.path.basename(path))
                if os.path.isfile(image_path):
                    self.send_response(200)
                    self.send_header('Content-type', 'image/png')
                    self.end_headers()
                    with open(image_path, 'rb') as f:
                        self.wfile.write(f.read())
                    return

            self._ok()
        except Exception as e:
            xbmc.log(f"[KronosCast] Handler exception: {e}", xbmc.LOGERROR)
            try:
                self.send_error(500, "Internal Server Error")
            except Exception:
                pass

    def do_POST(self):
        try:
            if self.path == "/upload":
                ctype, pdict = cgi.parse_header(self.headers.get('Content-Type', ''))
                if "torrent" in self.path.lower():
                    content_length = int(self.headers.get('Content-Length', "0"))
                    file_data = self.rfile.read(content_length)
                    torrent_path = os.path.join(TORRENT_DIR, "uploaded.torrent")
                    with open(torrent_path, 'wb') as f:
                        f.write(file_data)

                    if xbmc.Player().isPlayingAudio():
                        show_notification("[B]Kronos Cast[/B]", "Uploading Blocked. Audio Player Is Active.", is_error=True)
                        self._json({"status": "blocked", "reason": "audio_active"}, 423)
                        return

                    play_with_elementum(torrent_path, is_torrent=True, allow_blocked=False)
                    self._json({"status": "ok"})
                    return

                elif ctype == 'multipart/form-data':
                    pdict['boundary'] = bytes(pdict.get('boundary', ''), "utf-8")
                    if 'Content-Length' in self.headers:
                        pdict['CONTENT-LENGTH'] = int(self.headers['Content-Length'])

                    form = cgi.FieldStorage(
                        fp=self.rfile,
                        headers=self.headers,
                        environ={'REQUEST_METHOD': 'POST'},
                        keep_blank_values=True
                    )

                    if "file" in form:
                        upload_file = form["file"]
                        filename = upload_file.filename
                        file_data = upload_file.file.read()
                        ext = os.path.splitext(filename)[1].lower() if filename else ""

                        allowed_exts = ['.mp4', '.mkv', '.mp3', '.flac', '.wav', '.torrent']
                        if ext not in allowed_exts:
                            show_notification("[B]Kronos Cast[/B]", f"Unsupported file type: {ext}", is_error=True)
                            self._json({"status": "error", "reason": "unsupported"}, 400)
                            return

                        if ext in ['.mp3', '.flac', '.wav']:
                            target_folder = MUSIC_DIR
                        elif ext in ['.mp4', '.mkv']:
                            target_folder = VIDEO_DIR
                        elif ext == '.torrent':
                            target_folder = TORRENT_DIR
                        else:
                            self._json({"status": "error"}, 400)
                            return  # fallback safeguard

                        target_path = os.path.join(target_folder, filename)
                        with open(target_path, 'wb') as f:
                            f.write(file_data)

                        show_notification("[B]Kronos Cast[/B]", f"Uploaded: {filename}")

                        if ext == '.torrent':
                            if xbmc.Player().isPlayingAudio():
                                show_notification("[B]Kronos Cast[/B]", "Uploading Blocked. Audio Player Is Active.", is_error=True)
                                self._json({"status": "blocked", "reason": "audio_active"}, 423)
                                return
                            play_with_elementum(target_path, is_torrent=True, allow_blocked=False)

                        self._json({"status": "ok"})
                        return

            self._ok()
        except Exception as e:
            xbmc.log(f"[KronosCast] POST handler exception: {e}", xbmc.LOGERROR)
            try:
                self.send_error(500, "Internal Server Error")
            except Exception:
                pass

def run_server():
    global server, _current_port
    with _server_lock:
        port = _read_port()       # read fresh from settings
        _current_port = port      # remember for GUI/status
        for attempt in range(5):
            try:
                server = HTTPServer(("", port), RequestHandler)
                xbmc.log(f"[KronosCast] Web server running on port {port}", xbmc.LOGINFO)
                server.serve_forever()
                break
            except OSError as e:
                xbmc.log(f"[KronosCast] Port {port} busy, retrying in 3s... ({attempt + 1}/5)", xbmc.LOGWARNING)
                xbmc.sleep(3000)
            except Exception as e:
                xbmc.log(f"[KronosCast] Server error: {e}", xbmc.LOGERROR)
                break
        if server:
            try:
                server.server_close()
            except Exception:
                pass
        server = None

def stop_server():
    global server
    with _server_lock:
        if server is not None:
            try:
                xbmc.log("[KronosCast] Stopping web server...", xbmc.LOGINFO)
                server.shutdown()
            except Exception as e:
                xbmc.log(f"[KronosCast] Error stopping server: {e}", xbmc.LOGERROR)
 
if __name__ == "__main__":
    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()

    