import threading
import SocketServer
import xbmc
import xbmcaddon
import socket
from resources.lib.common import log
from resources.lib.MSLHttpRequestHandler import MSLHttpRequestHandler

def select_unused_port():
  s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  s.bind(('localhost', 0))
  addr, port = s.getsockname()
  s.close()
  return port

addon = xbmcaddon.Addon()
PORT = select_unused_port()
addon.setSetting('msl_service_port', str(PORT))
log("Picked Port: " + str(PORT))
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
