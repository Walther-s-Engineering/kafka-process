import os
import typing as t

import signal
import threading

import attrs

from multiprocessing.context import SpawnProcess
from types import FrameType

from tricky.typing import String

# NOTE: A lot of code taken from "uvicorn" framework, but rewritten.

HANDLED_SIGNALS = (
    signal.SIGINT,  # Unix signal 2. Sent by Ctrl+C.
    signal.SIGTERM,  # Unix signal 15. Sent by `kill <pid>`.
)


@attrs.define
class Multiprocess:
    config: t.Any
    target: t.Callable
    processes: t.List[SpawnProcess] = attrs.field(default=[])

    # FIXME: May need type annotation
    should_exit = threading.Event()
    pid = os.getpid()

    def signal_handler(
        self,
        sig: String,
        frame: t.Optional[FrameType],
    ) -> None:
        self.should_exit.set()
