from ssl import SSLContext
from typing import Optional

import anyio.abc
from anyio import BrokenResourceError, EndOfStream
from anyio.abc import ByteStream, SocketAttribute
from anyio.streams.tls import TLSAttribute, TLSStream

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
from .._utils import is_socket_readable
from .base import AsyncBackend, AsyncLock, AsyncSemaphore, AsyncSocketStream


class SocketStream(AsyncSocketStream):
    def __init__(self, stream: ByteStream) -> None:
        self.stream = stream
        self.read_lock = anyio.Lock()
        self.write_lock = anyio.Lock()

    def get_http_version(self) -> str:
        alpn_protocol = self.stream.extra(TLSAttribute.alpn_protocol, None)
        return "HTTP/2" if alpn_protocol == "h2" else "HTTP/1.1"

    async def start_tls(
        self,
        hostname: bytes,
        ssl_context: SSLContext,
        timeout: TimeoutDict,
    ) -> "SocketStream":
        connect_timeout = timeout.get("connect")
        try:
            with anyio.fail_after(connect_timeout):
                ssl_stream = await TLSStream.wrap(
                    self.stream,
                    ssl_context=ssl_context,
                    hostname=hostname.decode("ascii"),
                    standard_compatible=False,
                )
        except TimeoutError:
            raise ConnectTimeout from None
        except BrokenResourceError as exc:
            raise ConnectError from exc

        return SocketStream(ssl_stream)

    async def read(self, n: int, timeout: TimeoutDict) -> bytes:
        read_timeout = timeout.get("read")
        async with self.read_lock:
            try:
                with anyio.fail_after(read_timeout):
                    return await self.stream.receive(n)
            except TimeoutError:
                await self.stream.aclose()
                raise ReadTimeout from None
            except BrokenResourceError as exc:
                raise ReadError from exc
            except EndOfStream:
                return b""

    async def write(self, data: bytes, timeout: TimeoutDict) -> None:
        if not data:
            return

        write_timeout = timeout.get("write")
        async with self.write_lock:
            try:
                with anyio.fail_after(write_timeout):
                    return await self.stream.send(data)
            except TimeoutError:
                await self.stream.aclose()
                raise WriteTimeout from None
            except BrokenResourceError as exc:
                raise WriteError from exc

    async def aclose(self) -> None:
        async with self.write_lock:
            try:
                await self.stream.aclose()
            except BrokenResourceError:
                pass

    def is_readable(self) -> bool:
        sock = self.stream.extra(SocketAttribute.raw_socket)
        return is_socket_readable(sock)


class Lock(AsyncLock):
    def __init__(self) -> None:
        self._lock = anyio.Lock()

    async def release(self) -> None:
        self._lock.release()

    async def acquire(self) -> None:
        await self._lock.acquire()


class Semaphore(AsyncSemaphore):
    def __init__(self, max_value: int, exc_class: type):
        self.max_value = max_value
        self.exc_class = exc_class

    @property
    def semaphore(self) -> anyio.abc.Semaphore:
        if not hasattr(self, "_semaphore"):
            self._semaphore = anyio.Semaphore(self.max_value)
        return self._semaphore

    async def acquire(self, timeout: float = None) -> None:
        with anyio.move_on_after(timeout):
            await self.semaphore.acquire()
            return

        raise self.exc_class()

    async def release(self) -> None:
        self.semaphore.release()


class AnyIOBackend(AsyncBackend):
    async def open_tcp_stream(
        self,
        hostname: bytes,
        port: int,
        ssl_context: Optional[SSLContext],
        timeout: TimeoutDict,
        *,
        local_address: Optional[str],
    ) -> AsyncSocketStream:
        connect_timeout = timeout.get("connect")
        unicode_host = hostname.decode("utf-8")
        exc_map = {
            TimeoutError: ConnectTimeout,
            OSError: ConnectError,
            BrokenResourceError: ConnectError,
        }

        with map_exceptions(exc_map):
            with anyio.fail_after(connect_timeout):
                stream: anyio.abc.ByteStream
                stream = await anyio.connect_tcp(
                    unicode_host, port, local_host=local_address
                )
                if ssl_context:
                    stream = await TLSStream.wrap(
                        stream,
                        hostname=unicode_host,
                        ssl_context=ssl_context,
                        standard_compatible=False,
                    )

        return SocketStream(stream=stream)

    async def open_uds_stream(
        self,
        path: str,
        hostname: bytes,
        ssl_context: Optional[SSLContext],
        timeout: TimeoutDict,
    ) -> AsyncSocketStream:
        connect_timeout = timeout.get("connect")
        unicode_host = hostname.decode("utf-8")
        exc_map = {
            TimeoutError: ConnectTimeout,
            OSError: ConnectError,
            BrokenResourceError: ConnectError,
        }

        with map_exceptions(exc_map):
            with anyio.fail_after(connect_timeout):
                stream: anyio.abc.ByteStream = await anyio.connect_unix(path)
                if ssl_context:
                    stream = await TLSStream.wrap(
                        stream,
                        hostname=unicode_host,
                        ssl_context=ssl_context,
                        standard_compatible=False,
                    )

        return SocketStream(stream=stream)

    def create_lock(self) -> AsyncLock:
        return Lock()

    def create_semaphore(self, max_value: int, exc_class: type) -> AsyncSemaphore:
        return Semaphore(max_value, exc_class=exc_class)

    async def time(self) -> float:
        return float(anyio.current_time())

    async def sleep(self, seconds: float) -> None:
        await anyio.sleep(seconds)
