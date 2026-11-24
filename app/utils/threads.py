"""Safe lifetime management for QThread workers.

Workers are kept referenced until they have actually finished, so a thread is
never garbage-collected (and therefore destroyed) while still running, and
nothing needs the unsafe ``QThread.terminate()``.
"""
from typing import Optional, Set

from PyQt6.QtCore import QObject, QThread

_threads: Set[QThread] = set()


class _Reaper(QObject):
    """Lives in the main thread; drops references to finished workers."""

    def reap(self):
        for t in [t for t in _threads if t.isFinished()]:
            _threads.discard(t)


_reaper: Optional[_Reaper] = None


def start(thread: QThread) -> None:
    """Start a worker thread and keep it alive until it finishes."""
    global _reaper
    if _reaper is None:
        _reaper = _Reaper()
    _threads.add(thread)
    thread.finished.connect(_reaper.reap)
    thread.start()


def wait_all(timeout_ms: int = 5000) -> None:
    """Block (briefly) until running workers finish, e.g. on app exit."""
    for t in list(_threads):
        t.wait(timeout_ms)
    if _reaper is not None:
        _reaper.reap()
