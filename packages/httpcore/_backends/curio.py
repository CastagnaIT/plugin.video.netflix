from ssl import SSLContext, SSLSocket
from typing import Optional

import curio
import curio.io

from .._exceptions import (
    ConnectError,
    ConnectTimeout,
    ReadError,
    ReadTimeout,
    WriteError,
    WriteTimeout,
    map_exceptions,
)
from .._types import TimeoutDict
from .._utils import get_logger, is_socket_readable
from .base import AsyncBackend, AsyncLock, AsyncSemaphore, AsyncSocketStream

logger = get_logger(__name__)

ONE_DAY_IN_SECONDS = float(60 * 60 * 24)


def convert_timeout(value: Optional[float]) -> float:
    return value if value is not None else ONE_DAY_IN_SECONDS


class Lock(AsyncLock):
    def __init__(self) -> None:
        self._lock = curio.Lock()

    async def acquire(self) -> None:
        await self._lock.acquire()

    async def release(self) -> None:
        await self._lock.release()


class Semaphore(AsyncSemaphore):
    def __init__(self, max_value: int, exc_class: type) -> None:
        self.max_value = max_value
        self.exc_class = exc_class

    @property
    def semaphore(self) -> curio.Semaphore:
        if not hasattr(self, "_semaphore"):
            self._semaphore = curio.Semaphore(value=self.max_value)
        return self._semaphore

    async def acquire(self, timeout: float = None) -> None:
        timeout = convert_timeout(timeout)

        try:
            return await curio.timeout_after(timeout, self.semaphore.acquire())
        except curio.TaskTimeout:
            raise self.exc_class()

    async def release(self) -> None:
        await self.semaphore.release()


class SocketStream(AsyncSocketStream):
    def __init__(self, socket: curio.io.Socket) -> None:
        self.read_lock = curio.Lock()
        self.write_lock = curio.Lock()
        self.socket = socket
        self.stream = socket.as_stream()

    def get_http_version(self) -> str:
        if hasattr(self.socket, "_socket"):
            raw_socket = self.socket._socket

            if isinstance(raw_socket, SSLSocket):
                ident = raw_socket.selected_alpn_protocol()
                return "HTTP/2" if ident == "h2" else "HTTP/1.1"

        return "HTTP/1.1"

    async def start_tls(
        self, hostname: bytes, ssl_context: SSLContext, timeout: TimeoutDict
    ) -> "AsyncSocketStream":
        connect_timeout = convert_timeout(timeout.get("connect"))
        exc_map = {
            curio.TaskTimeout: ConnectTimeout,
            curio.CurioError: ConnectError,
            OSError: ConnectError,
        }

        with map_exceptions(exc_map):
            wrapped_sock = curio.io.Socket(
                ssl_context.wrap_socket(
                    self.socket._socket,
                    do_handshake_on_connect=False,
                    server_hostname=hostname.decode("ascii"),
                )
            )

            await curio.timeout_after(
                connect_timeout,
                wrapped_sock.do_handshake(),
            )

            return SocketStream(wrapped_sock)

    async def read(self, n: int, timeout: TimeoutDict) -> bytes:
        read_timeout = convert_timeout(timeout.get("read"))
        exc_map = {
            curio.TaskTimeout: ReadTimeout,
            curio.CurioError: ReadError,
            OSError: ReadError,
        }

        with map_exceptions(exc_map):
            async with self.read_lock:
                return await curio.timeout_after(read_timeout, self.stream.read(n))

    async def write(self, data: bytes, timeout: TimeoutDict) -> None:
        write_timeout = convert_timeout(timeout.get("write"))
        exc_map = {
            curio.TaskTimeout: WriteTimeout,
            curio.CurioError: WriteError,
            OSError: WriteError,
        }

        with map_exceptions(exc_map):
            async with self.write_lock:
                await curio.timeout_after(write_timeout, self.stream.write(data))

    async def aclose(self) -> None:
        await self.stream.close()
        await self.socket.close()

    def is_readable(self) -> bool:
        return is_socket_readable(self.socket)


class CurioBackend(AsyncBackend):
    async def open_tcp_stream(
        self,
        hostname: bytes,
        port: int,
        ssl_context: Optional[SSLContext],
        timeout: TimeoutDict,
        *,
        local_address: Optional[str],
    ) -> AsyncSocketStream:
        connect_timeout = convert_timeout(timeout.get("connect"))
        exc_map = {
            curio.TaskTimeout: ConnectTimeout,
            curio.CurioError: ConnectError,
            OSError: ConnectError,
        }
        host = hostname.decode("ascii")

        kwargs: dict = {}
        if ssl_context is not None:
            kwargs["ssl"] = ssl_context
            kwargs["server_hostname"] = host
        if local_address is not None:
            kwargs["source_addr"] = (local_address, 0)

        with map_exceptions(exc_map):
            sock: curio.io.Socket = await curio.timeout_after(
                connect_timeout,
                curio.open_connection(hostname, port, **kwargs),
            )

            return SocketStream(sock)

    async def open_uds_stream(
        self,
        path: str,
        hostname: bytes,
        ssl_context: Optional[SSLContext],
        timeout: TimeoutDict,
    ) -> AsyncSocketStream:
        connect_timeout = convert_timeout(timeout.get("connect"))
        exc_map = {
            curio.TaskTimeout: ConnectTimeout,
            curio.CurioError: ConnectError,
            OSError: ConnectError,
        }
        host = hostname.decode("ascii")
        kwargs = (
            {} if ssl_context is None else {"ssl": ssl_context, "server_hostname": host}
        )

        with map_exceptions(exc_map):
            sock: curio.io.Socket = await curio.timeout_after(
                connect_timeout, curio.open_unix_connection(path, **kwargs)
            )

            return SocketStream(sock)

    def create_lock(self) -> AsyncLock:
        return Lock()

    def create_semaphore(self, max_value: int, exc_class: type) -> AsyncSemaphore:
        return Semaphore(max_value, exc_class)

    async def time(self) -> float:
        return await curio.clock()

    async def sleep(self, seconds: float) -> None:
        await curio.sleep(seconds)
