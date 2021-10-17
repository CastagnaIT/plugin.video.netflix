from ssl import SSLContext
from types import TracebackType
from typing import TYPE_CHECKING, Optional, Type

from .._types import TimeoutDict

if TYPE_CHECKING:  # pragma: no cover
    from .sync import SyncBackend


def lookup_async_backend(name: str) -> "AsyncBackend":
    if name == "auto":
        from .auto import AutoBackend

        return AutoBackend()
    elif name == "asyncio":
        from .asyncio import AsyncioBackend

        return AsyncioBackend()
    elif name == "trio":
        from .trio import TrioBackend

        return TrioBackend()
    elif name == "curio":
        from .curio import CurioBackend

        return CurioBackend()
    elif name == "anyio":
        from .anyio import AnyIOBackend

        return AnyIOBackend()

    raise ValueError("Invalid backend name {name!r}")


def lookup_sync_backend(name: str) -> "SyncBackend":
    from .sync import SyncBackend

    return SyncBackend()


class AsyncSocketStream:
    """
    A socket stream with read/write operations. Abstracts away any asyncio-specific
    interfaces into a more generic base class, that we can use with alternate
    backends, or for stand-alone test cases.
    """

    def get_http_version(self) -> str:
        raise NotImplementedError()  # pragma: no cover

    async def start_tls(
        self, hostname: bytes, ssl_context: SSLContext, timeout: TimeoutDict
    ) -> "AsyncSocketStream":
        raise NotImplementedError()  # pragma: no cover

    async def read(self, n: int, timeout: TimeoutDict) -> bytes:
        raise NotImplementedError()  # pragma: no cover

    async def write(self, data: bytes, timeout: TimeoutDict) -> None:
        raise NotImplementedError()  # pragma: no cover

    async def aclose(self) -> None:
        raise NotImplementedError()  # pragma: no cover

    def is_readable(self) -> bool:
        raise NotImplementedError()  # pragma: no cover


class AsyncLock:
    """
    An abstract interface for Lock classes.
    """

    async def __aenter__(self) -> None:
        await self.acquire()

    async def __aexit__(
        self,
        exc_type: Type[BaseException] = None,
        exc_value: BaseException = None,
        traceback: TracebackType = None,
    ) -> None:
        await self.release()

    async def release(self) -> None:
        raise NotImplementedError()  # pragma: no cover

    async def acquire(self) -> None:
        raise NotImplementedError()  # pragma: no cover


class AsyncSemaphore:
    """
    An abstract interface for Semaphore classes.
    Abstracts away any asyncio-specific interfaces.
    """

    async def acquire(self, timeout: float = None) -> None:
        raise NotImplementedError()  # pragma: no cover

    async def release(self) -> None:
        raise NotImplementedError()  # pragma: no cover


class AsyncBackend:
    async def open_tcp_stream(
        self,
        hostname: bytes,
        port: int,
        ssl_context: Optional[SSLContext],
        timeout: TimeoutDict,
        *,
        local_address: Optional[str],
    ) -> AsyncSocketStream:
        raise NotImplementedError()  # pragma: no cover

    async def open_uds_stream(
        self,
        path: str,
        hostname: bytes,
        ssl_context: Optional[SSLContext],
        timeout: TimeoutDict,
    ) -> AsyncSocketStream:
        raise NotImplementedError()  # pragma: no cover

    def create_lock(self) -> AsyncLock:
        raise NotImplementedError()  # pragma: no cover

    def create_semaphore(self, max_value: int, exc_class: type) -> AsyncSemaphore:
        raise NotImplementedError()  # pragma: no cover

    async def time(self) -> float:
        raise NotImplementedError()  # pragma: no cover

    async def sleep(self, seconds: float) -> None:
        raise NotImplementedError()  # pragma: no cover
