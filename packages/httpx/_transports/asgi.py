import typing
from urllib.parse import unquote

import sniffio

from .base import AsyncBaseTransport, AsyncByteStream

if typing.TYPE_CHECKING:  # pragma: no cover
    import asyncio

    import trio

    Event = typing.Union[asyncio.Event, trio.Event]


def create_event() -> "Event":
    if sniffio.current_async_library() == "trio":
        import trio

        return trio.Event()
    else:
        import asyncio

        return asyncio.Event()


class ASGIResponseStream(AsyncByteStream):
    def __init__(self, body: typing.List[bytes]) -> None:
        self._body = body

    async def __aiter__(self) -> typing.AsyncIterator[bytes]:
        yield b"".join(self._body)


class ASGITransport(AsyncBaseTransport):
    """
    A custom AsyncTransport that handles sending requests directly to an ASGI app.
    The simplest way to use this functionality is to use the `app` argument.

    ```
    client = httpx.AsyncClient(app=app)
    ```

    Alternatively, you can setup the transport instance explicitly.
    This allows you to include any additional configuration arguments specific
    to the ASGITransport class:

    ```
    transport = httpx.ASGITransport(
        app=app,
        root_path="/submount",
        client=("1.2.3.4", 123)
    )
    client = httpx.AsyncClient(transport=transport)
    ```

    Arguments:

    * `app` - The ASGI application.
    * `raise_app_exceptions` - Boolean indicating if exceptions in the application
       should be raised. Default to `True`. Can be set to `False` for use cases
       such as testing the content of a client 500 response.
    * `root_path` - The root path on which the ASGI application should be mounted.
    * `client` - A two-tuple indicating the client IP and port of incoming requests.
    ```
    """

    def __init__(
        self,
        app: typing.Callable,
        raise_app_exceptions: bool = True,
        root_path: str = "",
        client: typing.Tuple[str, int] = ("127.0.0.1", 123),
    ) -> None:
        self.app = app
        self.raise_app_exceptions = raise_app_exceptions
        self.root_path = root_path
        self.client = client

    async def handle_async_request(
        self,
        method: bytes,
        url: typing.Tuple[bytes, bytes, typing.Optional[int], bytes],
        headers: typing.List[typing.Tuple[bytes, bytes]],
        stream: AsyncByteStream,
        extensions: dict,
    ) -> typing.Tuple[
        int, typing.List[typing.Tuple[bytes, bytes]], AsyncByteStream, dict
    ]:
        # ASGI scope.
        scheme, host, port, full_path = url
        path, _, query = full_path.partition(b"?")
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method.decode(),
            "headers": [(k.lower(), v) for (k, v) in headers],
            "scheme": scheme.decode("ascii"),
            "path": unquote(path.decode("ascii")),
            "raw_path": path,
            "query_string": query,
            "server": (host.decode("ascii"), port),
            "client": self.client,
            "root_path": self.root_path,
        }

        # Request.
        request_body_chunks = stream.__aiter__()
        request_complete = False

        # Response.
        status_code = None
        response_headers = None
        body_parts = []
        response_started = False
        response_complete = create_event()

        # ASGI callables.

        async def receive() -> dict:
            nonlocal request_complete

            if request_complete:
                await response_complete.wait()
                return {"type": "http.disconnect"}

            try:
                body = await request_body_chunks.__anext__()
            except StopAsyncIteration:
                request_complete = True
                return {"type": "http.request", "body": b"", "more_body": False}
            return {"type": "http.request", "body": body, "more_body": True}

        async def send(message: dict) -> None:
            nonlocal status_code, response_headers, response_started

            if message["type"] == "http.response.start":
                assert not response_started

                status_code = message["status"]
                response_headers = message.get("headers", [])
                response_started = True

            elif message["type"] == "http.response.body":
                assert not response_complete.is_set()
                body = message.get("body", b"")
                more_body = message.get("more_body", False)

                if body and method != b"HEAD":
                    body_parts.append(body)

                if not more_body:
                    response_complete.set()

        try:
            await self.app(scope, receive, send)
        except Exception:
            if self.raise_app_exceptions or not response_complete.is_set():
                raise

        assert response_complete.is_set()
        assert status_code is not None
        assert response_headers is not None

        stream = ASGIResponseStream(body_parts)
        extensions = {}

        return (status_code, response_headers, stream, extensions)
