import enum
import time
from ssl import SSLContext
from typing import AsyncIterator, List, Optional, Tuple, Union, cast

import h11

from .._backends.auto import AsyncSocketStream
from .._bytestreams import AsyncIteratorByteStream
from .._exceptions import LocalProtocolError, RemoteProtocolError, map_exceptions
from .._types import URL, Headers, TimeoutDict
from .._utils import get_logger
from .base import AsyncByteStream, NewConnectionRequired
from .http import AsyncBaseHTTPConnection

H11Event = Union[
    h11.Request,
    h11.Response,
    h11.InformationalResponse,
    h11.Data,
    h11.EndOfMessage,
    h11.ConnectionClosed,
]


class ConnectionState(enum.IntEnum):
    NEW = 0
    ACTIVE = 1
    IDLE = 2
    CLOSED = 3


logger = get_logger(__name__)


class AsyncHTTP11Connection(AsyncBaseHTTPConnection):
    READ_NUM_BYTES = 64 * 1024

    def __init__(self, socket: AsyncSocketStream, keepalive_expiry: float = None):
        self.socket = socket

        self._keepalive_expiry: Optional[float] = keepalive_expiry
        self._should_expire_at: Optional[float] = None
        self._h11_state = h11.Connection(our_role=h11.CLIENT)
        self._state = ConnectionState.NEW

    def __repr__(self) -> str:
        return f"<AsyncHTTP11Connection [{self._state.name}]>"

    def _now(self) -> float:
        return time.monotonic()

    def _server_disconnected(self) -> bool:
        """
        Return True if the connection is idle, and the underlying socket is readable.
        The only valid state the socket can be readable here is when the b""
        EOF marker is about to be returned, indicating a server disconnect.
        """
        return self._state == ConnectionState.IDLE and self.socket.is_readable()

    def _keepalive_expired(self) -> bool:
        """
        Return True if the connection is idle, and has passed it's keepalive
        expiry time.
        """
        return (
            self._state == ConnectionState.IDLE
            and self._should_expire_at is not None
            and self._now() >= self._should_expire_at
        )

    def info(self) -> str:
        return f"HTTP/1.1, {self._state.name}"

    def should_close(self) -> bool:
        """
        Return `True` if the connection is in a state where it should be closed.
        """
        return self._server_disconnected() or self._keepalive_expired()

    def is_idle(self) -> bool:
        """
        Return `True` if the connection is currently idle.
        """
        return self._state == ConnectionState.IDLE

    def is_closed(self) -> bool:
        """
        Return `True` if the connection has been closed.
        """
        return self._state == ConnectionState.CLOSED

    def is_available(self) -> bool:
        """
        Return `True` if the connection is currently able to accept an outgoing request.
        """
        return self._state == ConnectionState.IDLE

    async def handle_async_request(
        self,
        method: bytes,
        url: URL,
        headers: Headers,
        stream: AsyncByteStream,
        extensions: dict,
    ) -> Tuple[int, Headers, AsyncByteStream, dict]:
        """
        Send a single HTTP/1.1 request.

        Note that there is no kind of task/thread locking at this layer of interface.
        Dealing with locking for concurrency is handled by the `AsyncHTTPConnection`.
        """
        timeout = cast(TimeoutDict, extensions.get("timeout", {}))

        if self._state in (ConnectionState.NEW, ConnectionState.IDLE):
            self._state = ConnectionState.ACTIVE
            self._should_expire_at = None
        else:
            raise NewConnectionRequired()

        await self._send_request(method, url, headers, timeout)
        await self._send_request_body(stream, timeout)
        (
            http_version,
            status_code,
            reason_phrase,
            headers,
        ) = await self._receive_response(timeout)
        response_stream = AsyncIteratorByteStream(
            aiterator=self._receive_response_data(timeout),
            aclose_func=self._response_closed,
        )
        extensions = {
            "http_version": http_version,
            "reason_phrase": reason_phrase,
        }
        return (status_code, headers, response_stream, extensions)

    async def start_tls(
        self, hostname: bytes, ssl_context: SSLContext, timeout: TimeoutDict = None
    ) -> AsyncSocketStream:
        timeout = {} if timeout is None else timeout
        self.socket = await self.socket.start_tls(hostname, ssl_context, timeout)
        return self.socket

    async def _send_request(
        self, method: bytes, url: URL, headers: Headers, timeout: TimeoutDict
    ) -> None:
        """
        Send the request line and headers.
        """
        logger.trace("send_request method=%r url=%r headers=%s", method, url, headers)
        _scheme, _host, _port, target = url
        with map_exceptions({h11.LocalProtocolError: LocalProtocolError}):
            event = h11.Request(method=method, target=target, headers=headers)
        await self._send_event(event, timeout)

    async def _send_request_body(
        self, stream: AsyncByteStream, timeout: TimeoutDict
    ) -> None:
        """
        Send the request body.
        """
        # Send the request body.
        async for chunk in stream:
            logger.trace("send_data=Data(<%d bytes>)", len(chunk))
            event = h11.Data(data=chunk)
            await self._send_event(event, timeout)

        # Finalize sending the request.
        event = h11.EndOfMessage()
        await self._send_event(event, timeout)

    async def _send_event(self, event: H11Event, timeout: TimeoutDict) -> None:
        """
        Send a single `h11` event to the network, waiting for the data to
        drain before returning.
        """
        bytes_to_send = self._h11_state.send(event)
        await self.socket.write(bytes_to_send, timeout)

    async def _receive_response(
        self, timeout: TimeoutDict
    ) -> Tuple[bytes, int, bytes, List[Tuple[bytes, bytes]]]:
        """
        Read the response status and headers from the network.
        """
        while True:
            event = await self._receive_event(timeout)
            if isinstance(event, h11.Response):
                break

        http_version = b"HTTP/" + event.http_version

        # h11 version 0.11+ supports a `raw_items` interface to get the
        # raw header casing, rather than the enforced lowercase headers.
        headers = event.headers.raw_items()

        return http_version, event.status_code, event.reason, headers

    async def _receive_response_data(
        self, timeout: TimeoutDict
    ) -> AsyncIterator[bytes]:
        """
        Read the response data from the network.
        """
        while True:
            event = await self._receive_event(timeout)
            if isinstance(event, h11.Data):
                logger.trace("receive_event=Data(<%d bytes>)", len(event.data))
                yield bytes(event.data)
            elif isinstance(event, (h11.EndOfMessage, h11.PAUSED)):
                logger.trace("receive_event=%r", event)
                break

    async def _receive_event(self, timeout: TimeoutDict) -> H11Event:
        """
        Read a single `h11` event, reading more data from the network if needed.
        """
        while True:
            with map_exceptions({h11.RemoteProtocolError: RemoteProtocolError}):
                event = self._h11_state.next_event()

            if event is h11.NEED_DATA:
                data = await self.socket.read(self.READ_NUM_BYTES, timeout)

                # If we feed this case through h11 we'll raise an exception like:
                #
                #     httpcore.RemoteProtocolError: can't handle event type
                #     ConnectionClosed when role=SERVER and state=SEND_RESPONSE
                #
                # Which is accurate, but not very informative from an end-user
                # perspective. Instead we handle messaging for this case distinctly.
                if data == b"" and self._h11_state.their_state == h11.SEND_RESPONSE:
                    msg = "Server disconnected without sending a response."
                    raise RemoteProtocolError(msg)

                self._h11_state.receive_data(data)
            else:
                assert event is not h11.NEED_DATA
                break
        return event

    async def _response_closed(self) -> None:
        logger.trace(
            "response_closed our_state=%r their_state=%r",
            self._h11_state.our_state,
            self._h11_state.their_state,
        )
        if (
            self._h11_state.our_state is h11.DONE
            and self._h11_state.their_state is h11.DONE
        ):
            self._h11_state.start_next_cycle()
            self._state = ConnectionState.IDLE
            if self._keepalive_expiry is not None:
                self._should_expire_at = self._now() + self._keepalive_expiry
        else:
            await self.aclose()

    async def aclose(self) -> None:
        if self._state != ConnectionState.CLOSED:
            self._state = ConnectionState.CLOSED

            if self._h11_state.our_state is h11.MUST_CLOSE:
                event = h11.ConnectionClosed()
                self._h11_state.send(event)

            await self.socket.aclose()
