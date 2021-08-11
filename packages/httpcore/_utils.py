import itertools
import logging
import os
import select
import socket
import sys
import typing

from ._types import URL, Origin

_LOGGER_INITIALIZED = False
TRACE_LOG_LEVEL = 5
DEFAULT_PORTS = {b"http": 80, b"https": 443}


class Logger(logging.Logger):
    # Stub for type checkers.
    def trace(self, message: str, *args: typing.Any, **kwargs: typing.Any) -> None:
        ...  # pragma: nocover


def get_logger(name: str) -> Logger:
    """
    Get a `logging.Logger` instance, and optionally
    set up debug logging based on the HTTPCORE_LOG_LEVEL or HTTPX_LOG_LEVEL
    environment variables.
    """
    global _LOGGER_INITIALIZED
    if not _LOGGER_INITIALIZED:
        _LOGGER_INITIALIZED = True
        logging.addLevelName(TRACE_LOG_LEVEL, "TRACE")

        log_level = os.environ.get(
            "HTTPCORE_LOG_LEVEL", os.environ.get("HTTPX_LOG_LEVEL", "")
        ).upper()
        if log_level in ("DEBUG", "TRACE"):
            logger = logging.getLogger("httpcore")
            logger.setLevel(logging.DEBUG if log_level == "DEBUG" else TRACE_LOG_LEVEL)
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(
                logging.Formatter(
                    fmt="%(levelname)s [%(asctime)s] %(name)s - %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            logger.addHandler(handler)

    logger = logging.getLogger(name)

    def trace(message: str, *args: typing.Any, **kwargs: typing.Any) -> None:
        logger.log(TRACE_LOG_LEVEL, message, *args, **kwargs)

    logger.trace = trace  # type: ignore

    return typing.cast(Logger, logger)


def url_to_origin(url: URL) -> Origin:
    scheme, host, explicit_port = url[:3]
    default_port = DEFAULT_PORTS[scheme]
    port = default_port if explicit_port is None else explicit_port
    return scheme, host, port


def origin_to_url_string(origin: Origin) -> str:
    scheme, host, explicit_port = origin
    port = f":{explicit_port}" if explicit_port != DEFAULT_PORTS[scheme] else ""
    return f"{scheme.decode('ascii')}://{host.decode('ascii')}{port}"


def exponential_backoff(factor: float) -> typing.Iterator[float]:
    yield 0
    for n in itertools.count(2):
        yield factor * (2 ** (n - 2))


def is_socket_readable(sock: typing.Optional[socket.socket]) -> bool:
    """
    Return whether a socket, as identifed by its file descriptor, is readable.

    "A socket is readable" means that the read buffer isn't empty, i.e. that calling
    .recv() on it would immediately return some data.
    """
    # NOTE: we want check for readability without actually attempting to read, because
    # we don't want to block forever if it's not readable.

    # In the case that the socket no longer exists, or cannot return a file
    # descriptor, we treat it as being readable, as if it the next read operation
    # on it is ready to return the terminating `b""`.
    sock_fd = None if sock is None else sock.fileno()
    if sock_fd is None or sock_fd < 0:
        return True

    # The implementation below was stolen from:
    # https://github.com/python-trio/trio/blob/20ee2b1b7376db637435d80e266212a35837ddcc/trio/_socket.py#L471-L478
    # See also: https://github.com/encode/httpcore/pull/193#issuecomment-703129316

    # Use select.select on Windows, and when poll is unavailable and select.poll
    # everywhere else. (E.g. When eventlet is in use. See #327)
    if sys.platform == "win32" or getattr(select, "poll", None) is None:
        rready, _, _ = select.select([sock_fd], [], [], 0)
        return bool(rready)
    p = select.poll()
    p.register(sock_fd, select.POLLIN)
    return bool(p.poll(0))
