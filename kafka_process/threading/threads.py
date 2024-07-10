import threading
import typing as t

from tricky.typing import Float

__all__ = ("CallbackThread",)

ThreadedObject = t.TypeVar("ThreadedObject")


class CallbackThread(threading.Thread):
    def __init__(
        self,
        target: t.Optional[t.Callable] = None,
        callback: t.Optional[t.Callable] = None,
        **kwargs: t.Any,
    ) -> None:
        super().__init__(**kwargs)
        self.callback = callback

    def join(self, timeout: t.Optional[Float] = None) -> None:
        if self.callback is not None:
            self.callback()
        super().join(timeout=timeout)
