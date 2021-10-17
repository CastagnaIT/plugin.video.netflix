import warnings
from ssl import SSLContext
from typing import (
    Iterator,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Union,
    cast,
)

from .._backends.sync import SyncBackend, SyncLock, SyncSemaphore
from .._backends.base import lookup_sync_backend
from .._exceptions import LocalProtocolError, PoolTimeout, UnsupportedProtocol
from .._threadlock import ThreadLock
from .._types import URL, Headers, Origin, TimeoutDict
from .._utils import get_logger, origin_to_url_string, url_to_origin
from .base import SyncByteStream, SyncHTTPTransport, NewConnectionRequired
from .connection import SyncHTTPConnection

logger = get_logger(__name__)


class NullSemaphore(SyncSemaphore):
    def __init__(self) -> None:
        pass

    def acquire(self, timeout: float = None) -> None:
        return

    def release(self) -> None:
        return


class ResponseByteStream(SyncByteStream):
    def __init__(
        self,
        stream: SyncByteStream,
        connection: SyncHTTPConnection,
        callback: Callable,
    ) -> None:
        """
        A wrapper around the response stream that we return from
        `.handle_request()`.

        Ensures that when `stream.close()` is called, the connection pool
        is notified via a callback.
        """
        self.stream = stream
        self.connection = connection
        self.callback = callback

    def __iter__(self) -> Iterator[bytes]:
        for chunk in self.stream:
            yield chunk

    def close(self) -> None:
        try:
            # Call the underlying stream close callback.
            # This will be a call to `SyncHTTP11Connection._response_closed()`
            # or `SyncHTTP2Stream._response_closed()`.
            self.stream.close()
        finally:
            # Call the connection pool close callback.
            # This will be a call to `SyncConnectionPool._response_closed()`.
            self.callback(self.connection)


class SyncConnectionPool(SyncHTTPTransport):
    """
    A connection pool for making HTTP requests.

    Parameters
    ----------
    ssl_context:
        An SSL context to use for verifying connections.
    max_connections:
        The maximum number of concurrent connections to allow.
    max_keepalive_connections:
        The maximum number of connections to allow before closing keep-alive
        connections.
    keepalive_expiry:
        The maximum time to allow before closing a keep-alive connection.
    http1:
        Enable/Disable HTTP/1.1 support. Defaults to True.
    http2:
        Enable/Disable HTTP/2 support. Defaults to False.
    uds:
        Path to a Unix Domain Socket to use instead of TCP sockets.
    local_address:
        Local address to connect from. Can also be used to connect using a particular
        address family. Using ``local_address="0.0.0.0"`` will connect using an
        ``AF_INET`` address (IPv4), while using ``local_address="::"`` will connect
        using an ``AF_INET6`` address (IPv6).
    retries:
        The maximum number of retries when trying to establish a connection.
    backend:
        A name indicating which concurrency backend to use.
    """

    def __init__(
        self,
        ssl_context: SSLContext = None,
        max_connections: int = None,
        max_keepalive_connections: int = None,
        keepalive_expiry: float = None,
        http1: bool = True,
        http2: bool = False,
        uds: str = None,
        local_address: str = None,
        retries: int = 0,
        max_keepalive: int = None,
        backend: Union[SyncBackend, str] = "sync",
    ):
        if max_keepalive is not None:
            warnings.warn(
                "'max_keepalive' is deprecated. Use 'max_keepalive_connections'.",
                DeprecationWarning,
            )
            max_keepalive_connections = max_keepalive

        if isinstance(backend, str):
            backend = lookup_sync_backend(backend)

        self._ssl_context = SSLContext() if ssl_context is None else ssl_context
        self._max_connections = max_connections
        self._max_keepalive_connections = max_keepalive_connections
        self._keepalive_expiry = keepalive_expiry
        self._http1 = http1
        self._http2 = http2
        self._uds = uds
        self._local_address = local_address
        self._retries = retries
        self._connections: Dict[Origin, Set[SyncHTTPConnection]] = {}
        self._thread_lock = ThreadLock()
        self._backend = backend
        self._next_keepalive_check = 0.0

        if not (http1 or http2):
            raise ValueError("Either http1 or http2 must be True.")

        if http2:
            try:
                import h2  # noqa: F401
            except ImportError:
                raise ImportError(
                    "Attempted to use http2=True, but the 'h2' "
                    "package is not installed. Use 'pip install httpcore[http2]'."
                )

    @property
    def _connection_semaphore(self) -> SyncSemaphore:
        # We do this lazily, to make sure backend autodetection always
        # runs within an async context.
        if not hasattr(self, "_internal_semaphore"):
            if self._max_connections is not None:
                self._internal_semaphore = self._backend.create_semaphore(
                    self._max_connections, exc_class=PoolTimeout
                )
            else:
                self._internal_semaphore = NullSemaphore()

        return self._internal_semaphore

    @property
    def _connection_acquiry_lock(self) -> SyncLock:
        if not hasattr(self, "_internal_connection_acquiry_lock"):
            self._internal_connection_acquiry_lock = self._backend.create_lock()
        return self._internal_connection_acquiry_lock

    def _create_connection(
        self,
        origin: Tuple[bytes, bytes, int],
    ) -> SyncHTTPConnection:
        return SyncHTTPConnection(
            origin=origin,
            http1=self._http1,
            http2=self._http2,
            keepalive_expiry=self._keepalive_expiry,
            uds=self._uds,
            ssl_context=self._ssl_context,
            local_address=self._local_address,
            retries=self._retries,
            backend=self._backend,
        )

    def handle_request(
        self,
        method: bytes,
        url: URL,
        headers: Headers,
        stream: SyncByteStream,
        extensions: dict,
    ) -> Tuple[int, Headers, SyncByteStream, dict]:
        if url[0] not in (b"http", b"https"):
            scheme = url[0].decode("latin-1")
            host = url[1].decode("latin-1")
            if scheme == "":
                raise UnsupportedProtocol(
                    f"The request to '://{host}/' is missing either an 'http://' \
                        or 'https://' protocol."
                )
            else:
                raise UnsupportedProtocol(
                    f"The request to '{scheme}://{host}' has \
                        an unsupported protocol {scheme!r}"
                )

        if not url[1]:
            raise LocalProtocolError("Missing hostname in URL.")

        origin = url_to_origin(url)
        timeout = cast(TimeoutDict, extensions.get("timeout", {}))

        self._keepalive_sweep()

        connection: Optional[SyncHTTPConnection] = None
        while connection is None:
            with self._connection_acquiry_lock:
                # We get-or-create a connection as an atomic operation, to ensure
                # that HTTP/2 requests issued in close concurrency will end up
                # on the same connection.
                logger.trace("get_connection_from_pool=%r", origin)
                connection = self._get_connection_from_pool(origin)

                if connection is None:
                    connection = self._create_connection(origin=origin)
                    logger.trace("created connection=%r", connection)
                    self._add_to_pool(connection, timeout=timeout)
                else:
                    logger.trace("reuse connection=%r", connection)

            try:
                response = connection.handle_request(
                    method, url, headers=headers, stream=stream, extensions=extensions
                )
            except NewConnectionRequired:
                connection = None
            except BaseException:  # noqa: PIE786
                # See https://github.com/encode/httpcore/pull/305 for motivation
                # behind catching 'BaseException' rather than 'Exception' here.
                logger.trace("remove from pool connection=%r", connection)
                self._remove_from_pool(connection)
                raise

        status_code, headers, stream, extensions = response
        wrapped_stream = ResponseByteStream(
            stream, connection=connection, callback=self._response_closed
        )
        return status_code, headers, wrapped_stream, extensions

    def _get_connection_from_pool(
        self, origin: Origin
    ) -> Optional[SyncHTTPConnection]:
        # Determine expired keep alive connections on this origin.
        reuse_connection = None
        connections_to_close = set()

        for connection in self._connections_for_origin(origin):
            if connection.should_close():
                connections_to_close.add(connection)
                self._remove_from_pool(connection)
            elif connection.is_available():
                reuse_connection = connection

        # Close any dropped connections.
        for connection in connections_to_close:
            connection.close()

        return reuse_connection

    def _response_closed(self, connection: SyncHTTPConnection) -> None:
        remove_from_pool = False
        close_connection = False

        if connection.is_closed():
            remove_from_pool = True
        elif connection.is_idle():
            num_connections = len(self._get_all_connections())
            if (
                self._max_keepalive_connections is not None
                and num_connections > self._max_keepalive_connections
            ):
                remove_from_pool = True
                close_connection = True

        if remove_from_pool:
            self._remove_from_pool(connection)

        if close_connection:
            connection.close()

    def _keepalive_sweep(self) -> None:
        """
        Remove any IDLE connections that have expired past their keep-alive time.
        """
        if self._keepalive_expiry is None:
            return

        now = self._backend.time()
        if now < self._next_keepalive_check:
            return

        self._next_keepalive_check = now + min(1.0, self._keepalive_expiry)
        connections_to_close = set()

        for connection in self._get_all_connections():
            if connection.should_close():
                connections_to_close.add(connection)
                self._remove_from_pool(connection)

        for connection in connections_to_close:
            connection.close()

    def _add_to_pool(
        self, connection: SyncHTTPConnection, timeout: TimeoutDict
    ) -> None:
        logger.trace("adding connection to pool=%r", connection)
        self._connection_semaphore.acquire(timeout=timeout.get("pool", None))
        with self._thread_lock:
            self._connections.setdefault(connection.origin, set())
            self._connections[connection.origin].add(connection)

    def _remove_from_pool(self, connection: SyncHTTPConnection) -> None:
        logger.trace("removing connection from pool=%r", connection)
        with self._thread_lock:
            if connection in self._connections.get(connection.origin, set()):
                self._connection_semaphore.release()
                self._connections[connection.origin].remove(connection)
                if not self._connections[connection.origin]:
                    del self._connections[connection.origin]

    def _connections_for_origin(self, origin: Origin) -> Set[SyncHTTPConnection]:
        return set(self._connections.get(origin, set()))

    def _get_all_connections(self) -> Set[SyncHTTPConnection]:
        connections: Set[SyncHTTPConnection] = set()
        for connection_set in self._connections.values():
            connections |= connection_set
        return connections

    def close(self) -> None:
        connections = self._get_all_connections()
        for connection in connections:
            self._remove_from_pool(connection)

        # Close all connections
        for connection in connections:
            connection.close()

    def get_connection_info(self) -> Dict[str, List[str]]:
        """
        Returns a dict of origin URLs to a list of summary strings for each connection.
        """
        self._keepalive_sweep()

        stats = {}
        for origin, connections in self._connections.items():
            stats[origin_to_url_string(origin)] = sorted(
                [connection.info() for connection in connections]
            )
        return stats
