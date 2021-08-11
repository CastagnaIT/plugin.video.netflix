from typing import AsyncIterator, Callable, Iterator

from ._async.base import AsyncByteStream
from ._sync.base import SyncByteStream


class ByteStream(AsyncByteStream, SyncByteStream):
    """
    A concrete implementation for either sync or async byte streams.

    Example::

        stream = httpcore.ByteStream(b"123")

    Parameters
    ----------
    content:
        A plain byte string used as the content of the stream.
    """

    def __init__(self, content: bytes) -> None:
        self._content = content

    def __iter__(self) -> Iterator[bytes]:
        yield self._content

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield self._content


class IteratorByteStream(SyncByteStream):
    """
    A concrete implementation for sync byte streams.

    Example::

        def generate_content():
            yield b"Hello, world!"
            ...

        stream = httpcore.IteratorByteStream(generate_content())

    Parameters
    ----------
    iterator:
        A sync byte iterator, used as the content of the stream.
    close_func:
        An optional function called when closing the stream.
    """

    def __init__(self, iterator: Iterator[bytes], close_func: Callable = None) -> None:
        self._iterator = iterator
        self._close_func = close_func

    def __iter__(self) -> Iterator[bytes]:
        for chunk in self._iterator:
            yield chunk

    def close(self) -> None:
        if self._close_func is not None:
            self._close_func()


class AsyncIteratorByteStream(AsyncByteStream):
    """
    A concrete implementation for async byte streams.

    Example::

        async def generate_content():
            yield b"Hello, world!"
            ...

        stream = httpcore.AsyncIteratorByteStream(generate_content())

    Parameters
    ----------
    aiterator:
        An async byte iterator, used as the content of the stream.
    aclose_func:
        An optional async function called when closing the stream.
    """

    def __init__(
        self, aiterator: AsyncIterator[bytes], aclose_func: Callable = None
    ) -> None:
        self._aiterator = aiterator
        self._aclose_func = aclose_func

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self._aiterator:
            yield chunk

    async def aclose(self) -> None:
        if self._aclose_func is not None:
            await self._aclose_func()
