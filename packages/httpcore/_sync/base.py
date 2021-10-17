import enum
from types import TracebackType
from typing import Iterator, Tuple, Type

from .._types import URL, Headers, T


class NewConnectionRequired(Exception):
    pass


class ConnectionState(enum.IntEnum):
    """
    PENDING  READY
        |    |   ^
        v    V   |
        ACTIVE   |
         |  |    |
         |  V    |
         V  IDLE-+
       FULL   |
         |    |
         V    V
         CLOSED
    """

    PENDING = 0  # Connection not yet acquired.
    READY = 1  # Re-acquired from pool, about to send a request.
    ACTIVE = 2  # Active requests.
    FULL = 3  # Active requests, no more stream IDs available.
    IDLE = 4  # No active requests.
    CLOSED = 5  # Connection closed.


class SyncByteStream:
    """
    The base interface for request and response bodies.

    Concrete implementations should subclass this class, and implement
    the :meth:`__iter__` method, and optionally the :meth:`close` method.
    """

    def __iter__(self) -> Iterator[bytes]:
        """
        Yield bytes representing the request or response body.
        """
        yield b""  # pragma: nocover

    def close(self) -> None:
        """
        Must be called by the client to indicate that the stream has been closed.
        """
        pass  # pragma: nocover

    def read(self) -> bytes:
        try:
            return b"".join([part for part in self])
        finally:
            self.close()


class SyncHTTPTransport:
    """
    The base interface for sending HTTP requests.

    Concrete implementations should subclass this class, and implement
    the :meth:`handle_request` method, and optionally the :meth:`close` method.
    """

    def handle_request(
        self,
        method: bytes,
        url: URL,
        headers: Headers,
        stream: SyncByteStream,
        extensions: dict,
    ) -> Tuple[int, Headers, SyncByteStream, dict]:
        """
        The interface for sending a single HTTP request, and returning a response.

        Parameters
        ----------
        method:
            The HTTP method, such as ``b'GET'``.
        url:
            The URL as a 4-tuple of (scheme, host, port, path).
        headers:
            Any HTTP headers to send with the request.
        stream:
            The body of the HTTP request.
        extensions:
            A dictionary of optional extensions.

        Returns
        -------
        status_code:
            The HTTP status code, such as ``200``.
        headers:
            Any HTTP headers included on the response.
        stream:
            The body of the HTTP response.
        extensions:
            A dictionary of optional extensions.
        """
        raise NotImplementedError()  # pragma: nocover

    def close(self) -> None:
        """
        Close the implementation, which should close any outstanding response streams,
        and any keep alive connections.
        """

    def __enter__(self: T) -> T:
        return self

    def __exit__(
        self,
        exc_type: Type[BaseException] = None,
        exc_value: BaseException = None,
        traceback: TracebackType = None,
    ) -> None:
        self.close()
