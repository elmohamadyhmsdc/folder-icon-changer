import ctypes
import json
import os
import shutil
from typing import Optional

from app.config import undo_dir

_DESKTOP_INI = "desktop.ini"
_ICON_FILE = "folder.ico"

# Windows file attribute flags
_FILE_ATTRIBUTE_HIDDEN = 0x02
_FILE_ATTRIBUTE_SYSTEM = 0x04
_SHCNE_ASSOCCHANGED = 0x08000000
_SHCNF_IDLIST = 0x0000


def _set_attrs(path: str, attrs: int):
    ctypes.windll.kernel32.SetFileAttributesW(path, attrs)


def _refresh_explorer():
    ctypes.windll.shell32.SHChangeNotify(_SHCNE_ASSOCCHANGED, _SHCNF_IDLIST, None, None)


def apply(folder_path: str, ico_source: str) -> bool:
    """
    Copy ico_source into folder_path as folder.ico, write desktop.ini,
    and apply the necessary Windows attributes.
    Returns True on success.
    """
    try:
        # Save undo state BEFORE making changes
        _save_undo_state(folder_path)

        ico_dest = os.path.join(folder_path, _ICON_FILE)
        shutil.copy2(ico_source, ico_dest)
        _set_attrs(ico_dest, _FILE_ATTRIBUTE_HIDDEN | _FILE_ATTRIBUTE_SYSTEM)

        ini_path = os.path.join(folder_path, _DESKTOP_INI)

        # Remove old desktop.ini attributes so we can overwrite
        if os.path.exists(ini_path):
            _set_attrs(ini_path, 0x80)  # FILE_ATTRIBUTE_NORMAL

        with open(ini_path, "w", encoding="utf-16") as f:
            f.write("[.ShellClassInfo]\r\n")
            f.write(f"IconFile={_ICON_FILE}\r\n")
            f.write("IconIndex=0\r\n")
            f.write("ConfirmFileOp=0\r\n")

        _set_attrs(ini_path, _FILE_ATTRIBUTE_HIDDEN | _FILE_ATTRIBUTE_SYSTEM)
        _set_attrs(folder_path, _FILE_ATTRIBUTE_SYSTEM)

        _refresh_explorer()
        return True
    except Exception as e:
        return False


def undo(folder_path: str) -> bool:
    """Revert folder to its original icon state."""
    state = _load_undo_state(folder_path)
    if state is None:
        return False

    try:
        ini_path = os.path.join(folder_path, _DESKTOP_INI)
        ico_path = os.path.join(folder_path, _ICON_FILE)

        # Remove hidden/system attrs before deletion
        for p in [ini_path, ico_path]:
            if os.path.exists(p):
                _set_attrs(p, 0x80)
                os.remove(p)

        # Restore original desktop.ini if there was one
        if state.get("had_desktop_ini") and state.get("original_content"):
            with open(ini_path, "w", encoding="utf-16") as f:
                f.write(state["original_content"])
            _set_attrs(ini_path, _FILE_ATTRIBUTE_HIDDEN | _FILE_ATTRIBUTE_SYSTEM)

        # Restore original folder attributes
        original_attrs = state.get("original_folder_attrs", 0x10)  # DIRECTORY
        _set_attrs(folder_path, original_attrs)

        _refresh_explorer()
        _delete_undo_state(folder_path)
        return True
    except Exception:
        return False


def _undo_key(folder_path: str) -> str:
    import hashlib
    return hashlib.md5(folder_path.encode()).hexdigest() + ".json"


def _save_undo_state(folder_path: str):
    ini_path = os.path.join(folder_path, _DESKTOP_INI)
    state = {
        "folder_path": folder_path,
        "had_desktop_ini": os.path.exists(ini_path),
        "original_content": None,
        "original_folder_attrs": ctypes.windll.kernel32.GetFileAttributesW(folder_path),
    }
    if state["had_desktop_ini"]:
        try:
            with open(ini_path, "r", encoding="utf-16") as f:
                state["original_content"] = f.read()
        except Exception:
            try:
                with open(ini_path, "r", encoding="utf-8") as f:
                    state["original_content"] = f.read()
            except Exception:
                pass

    dest = os.path.join(undo_dir(), _undo_key(folder_path))
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(state, f)


def _load_undo_state(folder_path: str) -> Optional[dict]:
    path = os.path.join(undo_dir(), _undo_key(folder_path))
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _delete_undo_state(folder_path: str):
    path = os.path.join(undo_dir(), _undo_key(folder_path))
    if os.path.exists(path):
        os.remove(path)
