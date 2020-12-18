# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    HTTP Endpoint for Netflix session management

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import json
from http.server import BaseHTTPRequestHandler
from socketserver import TCPServer

import resources.lib.common as common
from resources.lib.services.nfsession.nfsession import NetflixSession
from resources.lib.utils.logging import LOG


class NetflixHttpRequestHandler(BaseHTTPRequestHandler):
    """Handles & translates requests from HTTP IPC to Netflix"""
    # pylint: disable=invalid-name
    def do_HEAD(self):
        """Answers head requests with a success code"""
        self.send_response(200)

    def do_POST(self):
        """Loads the data for the requested resource"""
        func_name = self.path[1:]
        LOG.debug('Handling HTTP POST IPC call to {}', func_name)
        length = int(self.headers.get('content-length', 0))
        data = json.loads(self.rfile.read(length)) or None
        try:
            result = self.server.netflix_session.http_ipc_slots[func_name](data)
            if isinstance(result, dict) and common.IPC_EXCEPTION_PLACEHOLDER in result:
                self.send_response(500, json.dumps(result))
                self.end_headers()
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(result).encode('utf-8'))
        except KeyError:
            self.send_response(500, json.dumps(
                common.ipc_convert_exc_to_json(class_name='SlotNotImplemented',
                                               message='The specified slot {} does not exist'.format(func_name))
            ))
            self.end_headers()

    def log_message(self, *args):  # pylint: disable=arguments-differ
        """Disable the BaseHTTPServer Log"""


class NetflixTCPServer(TCPServer):
    """Override TCPServer to allow usage of shared members"""
    def __init__(self, server_address):
        """Initialization of NetflixTCPServer"""
        LOG.info('Constructing NetflixTCPServer')
        self.netflix_session = NetflixSession()
        super().__init__(server_address, NetflixHttpRequestHandler)
