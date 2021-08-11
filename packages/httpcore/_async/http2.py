import enum
import time
from ssl import SSLContext
from typing import AsyncIterator, Dict, List, Optional, Tuple, cast

import h2.connection
import h2.events
from h2.config import H2Configuration
from h2.exceptions import NoAvailableStreamIDError
from h2.settings import SettingCodes, Settings

from .._backends.auto import AsyncBackend, AsyncLock, AsyncSemaphore, AsyncSocketStream
from .._bytestreams import AsyncIteratorByteStream
from .._exceptions import LocalProtocolError, PoolTimeout, RemoteProtocolError
from .._types import URL, Headers, TimeoutDict
from .._utils import get_logger
from .base import AsyncByteStream, NewConnectionRequired
from .http import AsyncBaseHTTPConnection

logger = get_logger(__name__)


class ConnectionState(enum.IntEnum):
    IDLE = 0
    ACTIVE = 1
    CLOSED = 2


class AsyncHTTP2Connection(AsyncBaseHTTPConnection):
    READ_NUM_BYTES = 64 * 1024
    CONFIG = H2Configuration(validate_inbound_headers=False)

    def __init__(
        self,
        socket: AsyncSocketStream,
        backend: AsyncBackend,
        keepalive_expiry: float = None,
    ):
        self.socket = socket

        self._backend = backend
        self._h2_state = h2.connection.H2Connection(config=self.CONFIG)

        self._sent_connection_init = False
        self._streams: Dict[int, AsyncHTTP2Stream] = {}
        self._events: Dict[int, List[h2.events.Event]] = {}

        self._keepalive_expiry: Optional[float] = keepalive_expiry
        self._should_expire_at: Optional[float] = None
        self._state = ConnectionState.ACTIVE
        self._exhausted_available_stream_ids = False

    def __repr__(self) -> str:
        return f"<AsyncHTTP2Connection [{self._state}]>"

    def info(self) -> str:
        return f"HTTP/2, {self._state.name}, {len(self._streams)} streams"

    def _now(self) -> float:
        return time.monotonic()

    def should_close(self) -> bool:
        """
        Return `True` if the connection is currently idle, and the keepalive
        timeout has passed.
        """
        return (
            self._state == ConnectionState.IDLE
            and self._should_expire_at is not None
            and self._now() >= self._should_expire_at
        )

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
        This occurs when any of the following occur:

        * The connection has not yet been opened, and HTTP/2 support is enabled.
          We don't *know* at this point if we'll end up on an HTTP/2 connection or
          not, but we *might* do, so we indicate availability.
        * The connection has been opened, and is currently idle.
        * The connection is open, and is an HTTP/2 connection. The connection must
          also not have exhausted the maximum total number of stream IDs.
        """
        return (
            self._state != ConnectionState.CLOSED
            and not self._exhausted_available_stream_ids
        )

    @property
    def init_lock(self) -> AsyncLock:
        # We do this lazily, to make sure backend autodetection always
        # runs within an async context.
        if not hasattr(self, "_initialization_lock"):
            self._initialization_lock = self._backend.create_lock()
        return self._initialization_lock

    @property
    def read_lock(self) -> AsyncLock:
        # We do this lazily, to make sure backend autodetection always
        # runs within an async context.
        if not hasattr(self, "_read_lock"):
            self._read_lock = self._backend.create_lock()
        return self._read_lock

    @property
    def max_streams_semaphore(self) -> AsyncSemaphore:
        # We do this lazily, to make sure backend autodetection always
        # runs within an async context.
        if not hasattr(self, "_max_streams_semaphore"):
            max_streams = self._h2_state.local_settings.max_concurrent_streams
            self._max_streams_semaphore = self._backend.create_semaphore(
                max_streams, exc_class=PoolTimeout
            )
        return self._max_streams_semaphore

    async def start_tls(
        self, hostname: bytes, ssl_context: SSLContext, timeout: TimeoutDict = None
    ) -> AsyncSocketStream:
        raise NotImplementedError("TLS upgrade not supported on HTTP/2 connections.")

    async def handle_async_request(
        self,
        method: bytes,
        url: URL,
        headers: Headers,
        stream: AsyncByteStream,
        extensions: dict,
    ) -> Tuple[int, Headers, AsyncByteStream, dict]:
        timeout = cast(TimeoutDict, extensions.get("timeout", {}))

        async with self.init_lock:
            if not self._sent_connection_init:
                # The very first stream is responsible for initiating the connection.
                self._state = ConnectionState.ACTIVE
                await self.send_connection_init(timeout)
                self._sent_connection_init = True

        await self.max_streams_semaphore.acquire()
        try:
            try:
                stream_id = self._h2_state.get_next_available_stream_id()
            except NoAvailableStreamIDError:
                self._exhausted_available_stream_ids = True
                raise NewConnectionRequired()
            else:
                self._state = ConnectionState.ACTIVE
                self._should_expire_at = None

            h2_stream = AsyncHTTP2Stream(stream_id=stream_id, connection=self)
            self._streams[stream_id] = h2_stream
            self._events[stream_id] = []
            return await h2_stream.handle_async_request(
                method, url, headers, stream, extensions
            )
        except Exception:  # noqa: PIE786
            await self.max_streams_semaphore.release()
            raise

    async def send_connection_init(self, timeout: TimeoutDict) -> None:
        """
        The HTTP/2 connection requires some initial setup before we can start
        using individual request/response streams on it.
        """
        # Need to set these manually here instead of manipulating via
        # __setitem__() otherwise the H2Connection will emit SettingsUpdate
        # frames in addition to sending the undesired defaults.
        self._h2_state.local_settings = Settings(
            client=True,
            initial_values={
                # Disable PUSH_PROMISE frames from the server since we don't do anything
                # with them for now.  Maybe when we support caching?
                SettingCodes.ENABLE_PUSH: 0,
                # These two are taken from h2 for safe defaults
                SettingCodes.MAX_CONCURRENT_STREAMS: 100,
                SettingCodes.MAX_HEADER_LIST_SIZE: 65536,
            },
        )

        # Some websites (*cough* Yahoo *cough*) balk at this setting being
        # present in the initial handshake since it's not defined in the original
        # RFC despite the RFC mandating ignoring settings you don't know about.
        del self._h2_state.local_settings[
            h2.settings.SettingCodes.ENABLE_CONNECT_PROTOCOL
        ]

        logger.trace("initiate_connection=%r", self)
        self._h2_state.initiate_connection()
        self._h2_state.increment_flow_control_window(2 ** 24)
        data_to_send = self._h2_state.data_to_send()
        await self.socket.write(data_to_send, timeout)

    def is_socket_readable(self) -> bool:
        return self.socket.is_readable()

    async def aclose(self) -> None:
        logger.trace("close_connection=%r", self)
        if self._state != ConnectionState.CLOSED:
            self._state = ConnectionState.CLOSED

            await self.socket.aclose()

    async def wait_for_outgoing_flow(self, stream_id: int, timeout: TimeoutDict) -> int:
        """
        Returns the maximum allowable outgoing flow for a given stream.
        If the allowable flow is zero, then waits on the network until
        WindowUpdated frames have increased the flow rate.
        https://tools.ietf.org/html/rfc7540#section-6.9
        """
        local_flow = self._h2_state.local_flow_control_window(stream_id)
        connection_flow = self._h2_state.max_outbound_frame_size
        flow = min(local_flow, connection_flow)
        while flow == 0:
            await self.receive_events(timeout)
            local_flow = self._h2_state.local_flow_control_window(stream_id)
            connection_flow = self._h2_state.max_outbound_frame_size
            flow = min(local_flow, connection_flow)
        return flow

    async def wait_for_event(
        self, stream_id: int, timeout: TimeoutDict
    ) -> h2.events.Event:
        """
        Returns the next event for a given stream.
        If no events are available yet, then waits on the network until
        an event is available.
        """
        async with self.read_lock:
            while not self._events[stream_id]:
                await self.receive_events(timeout)
        return self._events[stream_id].pop(0)

    async def receive_events(self, timeout: TimeoutDict) -> None:
        """
        Read some data from the network, and update the H2 state.
        """
        data = await self.socket.read(self.READ_NUM_BYTES, timeout)
        if data == b"":
            raise RemoteProtocolError("Server disconnected")

        events = self._h2_state.receive_data(data)
        for event in events:
            event_stream_id = getattr(event, "stream_id", 0)
            logger.trace("receive_event stream_id=%r event=%s", event_stream_id, event)

            if hasattr(event, "error_code"):
                raise RemoteProtocolError(event)

            if event_stream_id in self._events:
                self._events[event_stream_id].append(event)

        data_to_send = self._h2_state.data_to_send()
        await self.socket.write(data_to_send, timeout)

    async def send_headers(
        self, stream_id: int, headers: Headers, end_stream: bool, timeout: TimeoutDict
    ) -> None:
        logger.trace("send_headers stream_id=%r headers=%r", stream_id, headers)
        self._h2_state.send_headers(stream_id, headers, end_stream=end_stream)
        self._h2_state.increment_flow_control_window(2 ** 24, stream_id=stream_id)
        data_to_send = self._h2_state.data_to_send()
        await self.socket.write(data_to_send, timeout)

    async def send_data(
        self, stream_id: int, chunk: bytes, timeout: TimeoutDict
    ) -> None:
        logger.trace("send_data stream_id=%r chunk=%r", stream_id, chunk)
        self._h2_state.send_data(stream_id, chunk)
        data_to_send = self._h2_state.data_to_send()
        await self.socket.write(data_to_send, timeout)

    async def end_stream(self, stream_id: int, timeout: TimeoutDict) -> None:
        logger.trace("end_stream stream_id=%r", stream_id)
        self._h2_state.end_stream(stream_id)
        data_to_send = self._h2_state.data_to_send()
        await self.socket.write(data_to_send, timeout)

    async def acknowledge_received_data(
        self, stream_id: int, amount: int, timeout: TimeoutDict
    ) -> None:
        self._h2_state.acknowledge_received_data(amount, stream_id)
        data_to_send = self._h2_state.data_to_send()
        await self.socket.write(data_to_send, timeout)

    async def close_stream(self, stream_id: int) -> None:
        try:
            logger.trace("close_stream stream_id=%r", stream_id)
            del self._streams[stream_id]
            del self._events[stream_id]

            if not self._streams:
                if self._state == ConnectionState.ACTIVE:
                    if self._exhausted_available_stream_ids:
                        await self.aclose()
                    else:
                        self._state = ConnectionState.IDLE
                        if self._keepalive_expiry is not None:
                            self._should_expire_at = (
                                self._now() + self._keepalive_expiry
                            )
        finally:
            await self.max_streams_semaphore.release()


class AsyncHTTP2Stream:
    def __init__(self, stream_id: int, connection: AsyncHTTP2Connection) -> None:
        self.stream_id = stream_id
        self.connection = connection

    async def handle_async_request(
        self,
        method: bytes,
        url: URL,
        headers: Headers,
        stream: AsyncByteStream,
        extensions: dict,
    ) -> Tuple[int, Headers, AsyncByteStream, dict]:
        headers = [(k.lower(), v) for (k, v) in headers]
        timeout = cast(TimeoutDict, extensions.get("timeout", {}))

        # Send the request.
        seen_headers = set(key for key, value in headers)
        has_body = (
            b"content-length" in seen_headers or b"transfer-encoding" in seen_headers
        )

        await self.send_headers(method, url, headers, has_body, timeout)
        if has_body:
            await self.send_body(stream, timeout)

        # Receive the response.
        status_code, headers = await self.receive_response(timeout)
        response_stream = AsyncIteratorByteStream(
            aiterator=self.body_iter(timeout), aclose_func=self._response_closed
        )

        extensions = {
            "http_version": b"HTTP/2",
        }
        return (status_code, headers, response_stream, extensions)

    async def send_headers(
        self,
        method: bytes,
        url: URL,
        headers: Headers,
        has_body: bool,
        timeout: TimeoutDict,
    ) -> None:
        scheme, hostname, port, path = url

        # In HTTP/2 the ':authority' pseudo-header is used instead of 'Host'.
        # In order to gracefully handle HTTP/1.1 and HTTP/2 we always require
        # HTTP/1.1 style headers, and map them appropriately if we end up on
        # an HTTP/2 connection.
        authority = None

        for k, v in headers:
            if k == b"host":
                authority = v
                break

        if authority is None:
            # Mirror the same error we'd see with `h11`, so that the behaviour
            # is consistent. Although we're dealing with an `:authority`
            # pseudo-header by this point, from an end-user perspective the issue
            # is that the outgoing request needed to include a `host` header.
            raise LocalProtocolError("Missing mandatory Host: header")

        headers = [
            (b":method", method),
            (b":authority", authority),
            (b":scheme", scheme),
            (b":path", path),
        ] + [
            (k, v)
            for k, v in headers
            if k
            not in (
                b"host",
                b"transfer-encoding",
            )
        ]
        end_stream = not has_body

        await self.connection.send_headers(self.stream_id, headers, end_stream, timeout)

    async def send_body(self, stream: AsyncByteStream, timeout: TimeoutDict) -> None:
        async for data in stream:
            while data:
                max_flow = await self.connection.wait_for_outgoing_flow(
                    self.stream_id, timeout
                )
                chunk_size = min(len(data), max_flow)
                chunk, data = data[:chunk_size], data[chunk_size:]
                await self.connection.send_data(self.stream_id, chunk, timeout)

        await self.connection.end_stream(self.stream_id, timeout)

    async def receive_response(
        self, timeout: TimeoutDict
    ) -> Tuple[int, List[Tuple[bytes, bytes]]]:
        """
        Read the response status and headers from the network.
        """
        while True:
            event = await self.connection.wait_for_event(self.stream_id, timeout)
            if isinstance(event, h2.events.ResponseReceived):
                break

        status_code = 200
        headers = []
        for k, v in event.headers:
            if k == b":status":
                status_code = int(v.decode("ascii", errors="ignore"))
            elif not k.startswith(b":"):
                headers.append((k, v))

        return (status_code, headers)

    async def body_iter(self, timeout: TimeoutDict) -> AsyncIterator[bytes]:
        while True:
            event = await self.connection.wait_for_event(self.stream_id, timeout)
            if isinstance(event, h2.events.DataReceived):
                amount = event.flow_controlled_length
                await self.connection.acknowledge_received_data(
                    self.stream_id, amount, timeout
                )
                yield event.data
            elif isinstance(event, (h2.events.StreamEnded, h2.events.StreamReset)):
                break

    async def _response_closed(self) -> None:
        await self.connection.close_stream(self.stream_id)
