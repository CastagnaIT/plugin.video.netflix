# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2020 Stefano Gottardo (original implementation module)
    HTTP Endpoint for Netflix cache

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import json
from http.server import BaseHTTPRequestHandler
from socketserver import TCPServer

from resources.lib.common.exceptions import InvalidPathError
from resources.lib.globals import G
from resources.lib.utils.logging import LOG


class NetflixHttpRequestHandler(BaseHTTPRequestHandler):
    """Handles cache requests from add-on client-frontend instance"""

    def do_HEAD(self):
        """Answers head requests with a success code"""
        self.send_response(200)

    def do_POST(self):
        """Handle cache POST requests"""
        # The arguments of the method to call are stored in the 'Params' header
        params = json.loads(self.headers['Params'])
        # LOG.debug('Handling Cache HTTP POST IPC call to {} {}', self.path[1:], params.get('identifier'))
        try:
            if 'data' in params:
                # If argument 'data' exists, inject the data
                length = int(self.headers.get('content-length', 0))
                params['data'] = self.rfile.read(length) or None
            result = _call(G.CACHE_MANAGEMENT, self.path[1:], params)
            self.send_response(200)
            self.end_headers()
            if result is not None:
                self.wfile.write(result)
        except InvalidPathError:
            self.send_response(404)
            self.end_headers()
        except Exception as exc:  # pylint: disable=broad-except
            if exc.__class__.__name__ != 'CacheMiss':
                import traceback
                LOG.error(traceback.format_exc())
            self.send_response(500, exc.__class__.__name__)
            self.end_headers()

    def do_GET(self):
        """Handle cache GET requests"""
        params = json.loads(self.headers['Params'])
        # LOG.debug('Handling Cache HTTP GET IPC call to {} ({})', self.path[1:], params.get('identifier'))
        try:
            result = _call(G.CACHE_MANAGEMENT, self.path[1:], params)
            self.send_response(200)
            self.end_headers()
            if result is not None:
                self.wfile.write(result)
        except InvalidPathError:
            self.send_response(404)
            self.end_headers()
        except Exception as exc:  # pylint: disable=broad-except
            if exc.__class__.__name__ != 'CacheMiss':
                import traceback
                LOG.error(traceback.format_exc())
            self.send_response(500, exc.__class__.__name__)
            self.end_headers()

    def log_message(self, *args):  # pylint: disable=arguments-differ
        """Disable the BaseHTTPServer Log"""


def _call(instance, func_name, data):
    try:
        func = getattr(instance, func_name)
    except AttributeError as exc:
        raise InvalidPathError('Name of the method {} not found'.format(func_name)) from exc
    if isinstance(data, dict):
        return func(**data)
    if data is not None:
        return func(data)
    return func()


class CacheTCPServer(TCPServer):
    """Override TCPServer to allow usage of shared members"""
    def __init__(self, server_address):
        """Initialization of CacheTCPServer"""
        LOG.info('Constructing CacheTCPServer')
        super().__init__(server_address, NetflixHttpRequestHandler)
