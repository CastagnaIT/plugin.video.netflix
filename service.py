import threading
import SocketServer
import xbmc
import xbmcaddon
import socket
from resources.lib.KodiHelper import KodiHelper
from resources.lib.MSLHttpRequestHandler import MSLHttpRequestHandler

addon = xbmcaddon.Addon()
kodi_helper = KodiHelper(
    plugin_handle=None,
    base_url=None
)


def select_unused_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('localhost', 0))
    addr, port = sock.getsockname()
    sock.close()
    return port

port = select_unused_port()
addon.setSetting('msl_service_port', str(port))
kodi_helper.log(msg='Picked Port: ' + str(port))

#Config the HTTP Server
SocketServer.TCPServer.allow_reuse_address = True
server = SocketServer.TCPServer(('127.0.0.1', port), MSLHttpRequestHandler)
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
    kodi_helper.log(msg='Stopped MSL Service')
