import threading
import SocketServer
import xbmc
import xbmcaddon
import socket
from resources.lib.KodiHelper import KodiHelper
from resources.lib.MSLHttpRequestHandler import MSLHttpRequestHandler

def select_unused_port():
  s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  s.bind(('localhost', 0))
  addr, port = s.getsockname()
  s.close()
  return port

plugin_handle = int(sys.argv[1])
base_url = sys.argv[0]
addon = xbmcaddon.Addon()

kodi_helper = KodiHelper(
    plugin_handle=plugin_handle,
    base_url=base_url
)

PORT = select_unused_port()
addon.setSetting('msl_service_port', str(PORT))
kodi_helper.log(msg='Picked Port: ' + str(PORT))
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
    kodi_helper.log(msg='Stopped MSL Service')
