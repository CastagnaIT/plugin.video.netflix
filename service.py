#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Module: service
# Created on: 26.01.2017

import threading
import SocketServer
import xbmc
import socket
from xbmcaddon import Addon
from resources.lib.KodiHelper import KodiHelper
from resources.lib.MSLHttpRequestHandler import MSLHttpRequestHandler
from resources.lib.NetflixHttpRequestHandler import NetflixHttpRequestHandler

def select_unused_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('localhost', 0))
    addr, port = sock.getsockname()
    sock.close()
    return port

addon = Addon()
kodi_helper = KodiHelper()

msl_port = select_unused_port()
addon.setSetting('msl_service_port', str(msl_port))
kodi_helper.log(msg='[MSL] Picked Port: ' + str(msl_port))

ns_port = select_unused_port()
addon.setSetting('netflix_service_port', str(ns_port))
kodi_helper.log(msg='[NS] Picked Port: ' + str(ns_port))

# server defaults
SocketServer.TCPServer.allow_reuse_address = True

# configure the MSL Server
msl_server = SocketServer.TCPServer(('127.0.0.1', msl_port), MSLHttpRequestHandler)
msl_server.server_activate()
msl_server.timeout = 1

# configure the Netflix Data Server
nd_server = SocketServer.TCPServer(('127.0.0.1', ns_port), NetflixHttpRequestHandler)
nd_server.server_activate()
nd_server.timeout = 1

if __name__ == '__main__':
    monitor = xbmc.Monitor()

    msl_thread = threading.Thread(target=msl_server.serve_forever)
    msl_thread.daemon = True
    msl_thread.start()

    nd_thread = threading.Thread(target=nd_server.serve_forever)
    nd_thread.daemon = True
    nd_thread.start()

    while not monitor.abortRequested():
        if monitor.waitForAbort(5):
            msl_server.shutdown()
            nd_server.shutdown()
            break

    msl_server.server_close()
    msl_server.socket.close()
    msl_server.shutdown()
    kodi_helper.log(msg='Stopped MSL Service')

    nd_server.server_close()
    nd_server.socket.close()
    nd_server.shutdown()
    kodi_helper.log(msg='Stopped HTTP Service')
