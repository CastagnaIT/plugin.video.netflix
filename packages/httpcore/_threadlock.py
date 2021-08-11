import threading
from types import TracebackType
from typing import Type


class ThreadLock:
    """
    Provides thread safety when used as a sync context manager, or a
    no-op when used as an async context manager.
    """

    def __init__(self) -> None:
        self.lock = threading.Lock()

    def __enter__(self) -> None:
        self.lock.acquire()

    def __exit__(
        self,
        exc_type: Type[BaseException] = None,
        exc_value: BaseException = None,
        traceback: TracebackType = None,
    ) -> None:
        self.lock.release()

    async def __aenter__(self) -> None:
        pass

    async def __aexit__(
        self,
        exc_type: Type[BaseException] = None,
        exc_value: BaseException = None,
        traceback: TracebackType = None,
    ) -> None:
        pass
