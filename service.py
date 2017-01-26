import threading
import SocketServer
import xbmc
from resources.lib.common import log
from resources.lib.MSLHttpRequestHandler import MSLHttpRequestHandler

PORT = 8000
Handler = MSLHttpRequestHandler
SocketServer.TCPServer.allow_reuse_address = True
server = SocketServer.TCPServer(('127.0.0.1', PORT), Handler)
server.server_activate()
server.timeout = 1

if __name__ == '__main__':
    monitor = xbmc.Monitor()
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()

    while not monitor.abortRequested():
        if monitor.waitForAbort(5):
            server.shutdown()
            break

    server.server_close()
    server.socket.close()
    server.shutdown()
    log("Stopped MSL Service")
