import ctypes
import os
import subprocess
import sys


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> bool:
    """Ask Windows to start a new elevated instance of this app.

    Returns True only if the elevated process was actually launched. It returns
    False when the user declines the UAC prompt, so the caller should keep
    running instead of exiting.
    """
    try:
        script = os.path.abspath(sys.argv[0])
        params = subprocess.list2cmdline([script, *sys.argv[1:]])
        # ShellExecuteW returns a value > 32 on success.
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
        return int(rc) > 32
    except Exception:
        return False
