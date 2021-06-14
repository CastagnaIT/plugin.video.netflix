import socket
import threading
import time
from ssl import SSLContext
from types import TracebackType
from typing import Optional, Type

from .._exceptions import (
    ConnectError,
    ConnectTimeout,
    ReadError,
    ReadTimeout,
    WriteError,
    WriteTimeout,
    map_exceptions,
)
from .tcp_keep_alive import enable_tcp_keep_alive
from .._types import TimeoutDict
from .._utils import is_socket_readable


class SyncSocketStream:
    """
    A socket stream with read/write operations. Abstracts away any asyncio-specific
    interfaces into a more generic base class, that we can use with alternate
    backends, or for stand-alone test cases.
    """

    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self.read_lock = threading.Lock()
        self.write_lock = threading.Lock()

    def get_http_version(self) -> str:
        selected_alpn_protocol = getattr(self.sock, "selected_alpn_protocol", None)
        if selected_alpn_protocol is not None:
            ident = selected_alpn_protocol()
            return "HTTP/2" if ident == "h2" else "HTTP/1.1"
        return "HTTP/1.1"

    def start_tls(
        self, hostname: bytes, ssl_context: SSLContext, timeout: TimeoutDict
    ) -> "SyncSocketStream":
        connect_timeout = timeout.get("connect")
        exc_map = {socket.timeout: ConnectTimeout, socket.error: ConnectError}

        with map_exceptions(exc_map):
            self.sock.settimeout(connect_timeout)
            wrapped = ssl_context.wrap_socket(
                self.sock, server_hostname=hostname.decode("ascii")
            )

        return SyncSocketStream(wrapped)

    def read(self, n: int, timeout: TimeoutDict) -> bytes:
        read_timeout = timeout.get("read")
        exc_map = {socket.timeout: ReadTimeout, socket.error: ReadError}

        with self.read_lock:
            with map_exceptions(exc_map):
                self.sock.settimeout(read_timeout)
                return self.sock.recv(n)

    def write(self, data: bytes, timeout: TimeoutDict) -> None:
        write_timeout = timeout.get("write")
        exc_map = {socket.timeout: WriteTimeout, socket.error: WriteError}

        with self.write_lock:
            with map_exceptions(exc_map):
                while data:
                    self.sock.settimeout(write_timeout)
                    n = self.sock.send(data)
                    data = data[n:]

    def close(self) -> None:
        with self.write_lock:
            try:
                self.sock.close()
            except socket.error:
                pass

    def is_readable(self) -> bool:
        return is_socket_readable(self.sock)


class SyncLock:
    def __init__(self) -> None:
        self._lock = threading.Lock()

    def __enter__(self) -> None:
        self.acquire()

    def __exit__(
        self,
        exc_type: Type[BaseException] = None,
        exc_value: BaseException = None,
        traceback: TracebackType = None,
    ) -> None:
        self.release()

    def release(self) -> None:
        self._lock.release()

    def acquire(self) -> None:
        self._lock.acquire()


class SyncSemaphore:
    def __init__(self, max_value: int, exc_class: type) -> None:
        self.max_value = max_value
        self.exc_class = exc_class
        self._semaphore = threading.Semaphore(max_value)

    def acquire(self, timeout: float = None) -> None:
        if not self._semaphore.acquire(timeout=timeout):  # type: ignore
            raise self.exc_class()

    def release(self) -> None:
        self._semaphore.release()


class SyncBackend:
    def open_tcp_stream(
        self,
        hostname: bytes,
        port: int,
        ssl_context: Optional[SSLContext],
        timeout: TimeoutDict,
        *,
        local_address: Optional[str],
    ) -> SyncSocketStream:
        address = (hostname.decode("ascii"), port)
        connect_timeout = timeout.get("connect")
        source_address = None if local_address is None else (local_address, 0)
        exc_map = {socket.timeout: ConnectTimeout, socket.error: ConnectError}

        with map_exceptions(exc_map):
            sock = socket.create_connection(
                address, connect_timeout, source_address=source_address  # type: ignore
            )
            # Enable TCP Keep-Alive
            enable_tcp_keep_alive(sock)

            if ssl_context is not None:
                sock = ssl_context.wrap_socket(
                    sock, server_hostname=hostname.decode("ascii")
                )
            return SyncSocketStream(sock=sock)

    def open_uds_stream(
        self,
        path: str,
        hostname: bytes,
        ssl_context: Optional[SSLContext],
        timeout: TimeoutDict,
    ) -> SyncSocketStream:
        connect_timeout = timeout.get("connect")
        exc_map = {socket.timeout: ConnectTimeout, socket.error: ConnectError}

        with map_exceptions(exc_map):
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(connect_timeout)
            sock.connect(path)

            if ssl_context is not None:
                sock = ssl_context.wrap_socket(
                    sock, server_hostname=hostname.decode("ascii")
                )

            return SyncSocketStream(sock=sock)

    def create_lock(self) -> SyncLock:
        return SyncLock()

    def create_semaphore(self, max_value: int, exc_class: type) -> SyncSemaphore:
        return SyncSemaphore(max_value, exc_class=exc_class)

    def time(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)
