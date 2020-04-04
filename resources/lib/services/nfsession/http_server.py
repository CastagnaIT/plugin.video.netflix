# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    HTTP Endpoint for Netflix session management

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import json

try:  # Python 3
    from http.server import BaseHTTPRequestHandler
except ImportError:
    from BaseHTTPServer import BaseHTTPRequestHandler

try:  # Python 3
    from socketserver import TCPServer
except ImportError:
    from SocketServer import TCPServer

import resources.lib.common as common

from .nfsession import NetflixSession


class NetflixHttpRequestHandler(BaseHTTPRequestHandler):
    """Handles & translates requests from Inputstream to Netflix"""
    # pylint: disable=invalid-name, broad-except
    def do_HEAD(self):
        """Answers head requests with a success code"""
        self.send_response(200)

    def do_POST(self):
        """Loads the licence for the requested resource"""
        common.debug('Handling HTTP POST IPC call to {}', self.path[1:])
        func = getattr(NetflixSession, self.path[1:])
        length = int(self.headers.get('content-length', 0))
        data = json.loads(self.rfile.read(length)) or None
        result = func(self.server.netflix_session, data)
        if not isinstance(result, dict) or 'error' not in result:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(result).encode('utf-8'))
        else:
            self.send_response(500, json.dumps(result))
            self.end_headers()

    def log_message(self, *args):  # pylint: disable=arguments-differ
        """Disable the BaseHTTPServer Log"""


class NetflixTCPServer(TCPServer):
    """Override TCPServer to allow usage of shared members"""
    def __init__(self, server_address):
        """Initialization of MSLTCPServer"""
        common.info('Constructing NetflixTCPServer')
        self.netflix_session = NetflixSession()
        TCPServer.__init__(self, server_address, NetflixHttpRequestHandler)
