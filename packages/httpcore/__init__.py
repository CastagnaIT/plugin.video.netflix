from ._async.base import AsyncByteStream, AsyncHTTPTransport
from ._async.connection_pool import AsyncConnectionPool
from ._async.http_proxy import AsyncHTTPProxy
from ._bytestreams import AsyncIteratorByteStream, ByteStream, IteratorByteStream
from ._exceptions import (
    CloseError,
    ConnectError,
    ConnectTimeout,
    LocalProtocolError,
    NetworkError,
    PoolTimeout,
    ProtocolError,
    ProxyError,
    ReadError,
    ReadTimeout,
    RemoteProtocolError,
    TimeoutException,
    UnsupportedProtocol,
    WriteError,
    WriteTimeout,
)
from ._sync.base import SyncByteStream, SyncHTTPTransport
from ._sync.connection_pool import SyncConnectionPool
from ._sync.http_proxy import SyncHTTPProxy

__all__ = [
    "AsyncByteStream",
    "AsyncConnectionPool",
    "AsyncHTTPProxy",
    "AsyncHTTPTransport",
    "AsyncIteratorByteStream",
    "ByteStream",
    "CloseError",
    "ConnectError",
    "ConnectTimeout",
    "IteratorByteStream",
    "LocalProtocolError",
    "NetworkError",
    "PoolTimeout",
    "ProtocolError",
    "ProxyError",
    "ReadError",
    "ReadTimeout",
    "RemoteProtocolError",
    "SyncByteStream",
    "SyncConnectionPool",
    "SyncHTTPProxy",
    "SyncHTTPTransport",
    "TimeoutException",
    "UnsupportedProtocol",
    "WriteError",
    "WriteTimeout",
]
__version__ = "0.13.6"

__locals = locals()

for _name in __all__:
    if not _name.startswith("__"):
        # Save original source module, used by Sphinx.
        __locals[_name].__source_module__ = __locals[_name].__module__
        # Override module for prettier repr().
        setattr(__locals[_name], "__module__", "httpcore")  # noqa
