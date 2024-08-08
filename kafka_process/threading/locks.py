from __future__ import annotations

import threading
import typing as t

from tricky.typing import Bool, String


class CallbackLock:
    def __init__(
        self,
        callback: t.Optional[t.Callable] = None,
    ) -> None:
        self._lock = threading.Lock()
        self._callback = callback

    def locked(self) -> Bool:
        return self._lock.locked()

    def acquire(self, blocking=True, timeout=-1):
        self._lock.acquire(blocking, timeout)

    def release(self):
        self._lock.release()
        if self._callback is not None:
            self._callback()

    def set_callback(self, callback: t.Callable) -> None:
        self._callback = callback

    def __enter__(self) -> CallbackLock:
        self.acquire()
        return self

    def __exit__(self, exc_type: t.Type[Exception], exc_val: Exception, exc_tb: String) -> None:
        self.release()
