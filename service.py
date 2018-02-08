# -*- coding: utf-8 -*-
# Author: asciidisco
# Module: service
# Created on: 13.01.2017
# License: MIT https://goo.gl/5bMj3H

"""Kodi plugin for Netflix (https://netflix.com)"""


import threading
import socket
from SocketServer import TCPServer
from resources.lib.KodiHelper import KodiHelper
from resources.lib.KodiMonitor import KodiMonitor
from resources.lib.MSLHttpRequestHandler import MSLHttpRequestHandler
from resources.lib.NetflixHttpRequestHandler import NetflixHttpRequestHandler


def select_unused_port():
    """
    Helper function to select an unused port on the host machine

    :return: int - Free port
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('127.0.0.1', 0))
    _, port = sock.getsockname()
    sock.close()
    return port


# init kodi helper (for logging)
KODI_HELPER = KodiHelper()

# pick & store a port for the MSL service
MSL_PORT = select_unused_port()
KODI_HELPER.set_setting('msl_service_port', str(MSL_PORT))
KODI_HELPER.log(msg='[MSL] Picked Port: ' + str(MSL_PORT))

# pick & store a port for the internal Netflix HTTP proxy service
NS_PORT = select_unused_port()
KODI_HELPER.set_setting('netflix_service_port', str(NS_PORT))
KODI_HELPER.log(msg='[NS] Picked Port: ' + str(NS_PORT))

# server defaults
TCPServer.allow_reuse_address = True

# configure the MSL Server
MSL_SERVER = TCPServer(('127.0.0.1', MSL_PORT), MSLHttpRequestHandler)
MSL_SERVER.server_activate()
MSL_SERVER.timeout = 1

# configure the Netflix Data Server
NS_SERVER = TCPServer(('127.0.0.1', NS_PORT), NetflixHttpRequestHandler)
NS_SERVER.server_activate()
NS_SERVER.timeout = 1

if __name__ == '__main__':
    MONITOR = KodiMonitor(KODI_HELPER)

    # start thread for MLS servie
    MSL_THREAD = threading.Thread(target=MSL_SERVER.serve_forever)
    MSL_THREAD.daemon = True
    MSL_THREAD.start()

    # start thread for Netflix HTTP service
    NS_THREAD = threading.Thread(target=NS_SERVER.serve_forever)
    NS_THREAD.daemon = True
    NS_THREAD.start()

    # kill the services if kodi monitor tells us to
    while not MONITOR.abortRequested():
        MONITOR.update_playback_progress()

        if MONITOR.waitForAbort(5):
            MSL_SERVER.shutdown()
            NS_SERVER.shutdown()
            break

    # MSL service shutdown sequence
    MSL_SERVER.server_close()
    MSL_SERVER.socket.close()
    MSL_SERVER.shutdown()
    KODI_HELPER.log(msg='Stopped MSL Service')

    # Netflix service shutdown sequence
    NS_SERVER.server_close()
    NS_SERVER.socket.close()
    NS_SERVER.shutdown()
    KODI_HELPER.log(msg='Stopped HTTP Service')
