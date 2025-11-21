#twentytw93-KronosTeam
import xbmcgui
import xbmcaddon
import xbmcplugin
import sys
import os
import urllib.parse
import threading
import urllib.request

from default import run_server, stop_server, get_current_port  # no port logic here

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
ADDON_PATH = ADDON.getAddonInfo('path')
FANART = os.path.join(ADDON_PATH, "resources", "media", "kronos_cast.jpg")

server_thread = None
action_lock = threading.Lock()

def launch_cast():
    global server_thread

    with action_lock:
        if server_thread and server_thread.is_alive():
            xbmcgui.Dialog().ok("[B]Kronos Cast[/B]", "Cast Server is Already Running!")
            return

        try:
            server_thread = threading.Thread(target=run_server, daemon=True)
            server_thread.start()
            xbmcgui.Dialog().ok("[B]Kronos Cast[/B]", f"Cast Server Started on Port {get_current_port()}")
        except Exception as e:
            xbmcgui.Dialog().ok("[B]Kronos Cast[/B]", f"Failed to Start Cast Server:\n{str(e)}")

def stop_cast():
    global server_thread

    with action_lock:
        xbmc.executebuiltin("PlayerControl(Stop)")
        try:
            stop_server()  
        except Exception:
            pass
        if server_thread:
            server_thread.join(timeout=1.0)
        xbmcgui.Dialog().ok("[B]Kronos Cast[/B]", "Cast Server Stopped")

def restart_cast():
    stop_cast()
    launch_cast()

def delete_all():
    port = get_current_port()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/clear", timeout=2.5) as response:
            if response.status == 200:
                xbmcgui.Dialog().ok("[B]Cleanup Complete[/B]", "All Media Files got Deleted.")
            else:
                raise Exception(f"HTTP {response.status}")
    except Exception as e:
        xbmcgui.Dialog().ok("[B]Cleanup Failed[/B]", f"Error During Cleanup:\n{str(e)}")

def open_settings():
    try:
        ADDON.openSettings()
    except Exception as e:
        xbmcgui.Dialog().ok("[B]Kronos Cast[/B]", f"Failed to Open Settings:\n{str(e)}")

def router():
    args = dict(urllib.parse.parse_qsl(sys.argv[2][1:])) if len(sys.argv) > 2 else {}
    action = args.get("action")

    if action == "launch":
        launch_cast()
    elif action == "restart":
        restart_cast()
    elif action == "delete":
        delete_all()
    elif action == "settings":
        open_settings()
    else:
        build_menu()

def build_menu():
    menu_items = [
        ("[B]Start Casting[/B]", "launch", "launch.png"),
        ("[B]Restart[/B]", "restart", "restart.png"),
        ("[B]Delete Stored Files[/B]", "delete", "delete.png"),
        ("[B]Settings[/B]", "settings", "settings.png"),
    ]

    for label, action, icon in menu_items:
        listitem = xbmcgui.ListItem(label)
        listitem.setArt({
            "thumb": os.path.join(ADDON_PATH, "resources", "media", icon),
            "icon": os.path.join(ADDON_PATH, "resources", "media", icon),
            "fanart": FANART
        })
        url = f"plugin://{ADDON_ID}/?action={action}"
        xbmcplugin.addDirectoryItem(
            handle=int(sys.argv[1]),
            url=url,
            listitem=listitem,
            isFolder=False
        )

    xbmcplugin.endOfDirectory(int(sys.argv[1]))

if __name__ == "__main__":
    router()