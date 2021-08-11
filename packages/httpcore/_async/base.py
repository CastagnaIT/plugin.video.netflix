import enum
from types import TracebackType
from typing import AsyncIterator, Tuple, Type

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


class AsyncByteStream:
    """
    The base interface for request and response bodies.

    Concrete implementations should subclass this class, and implement
    the :meth:`__aiter__` method, and optionally the :meth:`aclose` method.
    """

    async def __aiter__(self) -> AsyncIterator[bytes]:
        """
        Yield bytes representing the request or response body.
        """
        yield b""  # pragma: nocover

    async def aclose(self) -> None:
        """
        Must be called by the client to indicate that the stream has been closed.
        """
        pass  # pragma: nocover

    async def aread(self) -> bytes:
        try:
            return b"".join([part async for part in self])
        finally:
            await self.aclose()


class AsyncHTTPTransport:
    """
    The base interface for sending HTTP requests.

    Concrete implementations should subclass this class, and implement
    the :meth:`handle_async_request` method, and optionally the :meth:`aclose` method.
    """

    async def handle_async_request(
        self,
        method: bytes,
        url: URL,
        headers: Headers,
        stream: AsyncByteStream,
        extensions: dict,
    ) -> Tuple[int, Headers, AsyncByteStream, dict]:
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

    async def aclose(self) -> None:
        """
        Close the implementation, which should close any outstanding response streams,
        and any keep alive connections.
        """

    async def __aenter__(self: T) -> T:
        return self

    async def __aexit__(
        self,
        exc_type: Type[BaseException] = None,
        exc_value: BaseException = None,
        traceback: TracebackType = None,
    ) -> None:
        await self.aclose()
