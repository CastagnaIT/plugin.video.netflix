# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2021 Stefano Gottardo (original implementation module)
    HTTP Server for Netflix session, cache, proxy for InputStream Adaptive

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import pickle
from http.server import BaseHTTPRequestHandler
from socketserver import TCPServer, ThreadingMixIn
from urllib.parse import urlparse, parse_qs, unquote

from resources.lib import common
from resources.lib.common import IPC_ENDPOINT_CACHE, IPC_ENDPOINT_NFSESSION, IPC_ENDPOINT_MSL, IPC_ENDPOINT_NFSESSION_TEST
from resources.lib.common.exceptions import InvalidPathError, CacheMiss, MetadataNotAvailable, SlotNotImplemented
from resources.lib.globals import G, remove_ver_suffix
from resources.lib.services.nfsession.nfsession import NetflixSession
from resources.lib.utils.logging import LOG


class NetflixHttpRequestHandler(BaseHTTPRequestHandler):
    """Handles and translates requests from IPC via HTTP"""
    # pylint: disable=invalid-name
    def do_HEAD(self):
        """Answers head requests with a success code"""
        self.send_response(200)

    def do_GET(self):
        LOG.debug('HTTP Server: received GET request {}', self.path)
        parsed_url = urlparse(self.path)
        params = parse_qs(parsed_url.query)
        endpoint, func_name = parsed_url.path.rsplit('/', 1)
        if endpoint == IPC_ENDPOINT_MSL:
            handle_msl_request(self, func_name, None, params)
        else:
            self.send_error(404, 'Not found')
            self.end_headers()

    def do_POST(self):
        LOG.debug('HTTP Server: received POST request {}', self.path)
        parsed_url = urlparse(self.path)
        endpoint, func_name = parsed_url.path.rsplit('/', 1)
        length = int(self.headers.get('content-length', 0))
        data = self.rfile.read(length) or None
        if endpoint == IPC_ENDPOINT_MSL:
            handle_msl_request(self, func_name, data)
        elif endpoint == IPC_ENDPOINT_CACHE:
            handle_cache_request(self, func_name, data)
        elif endpoint == IPC_ENDPOINT_NFSESSION:
            handle_request(self, self.server.netflix_session, func_name, data)
        elif endpoint == IPC_ENDPOINT_NFSESSION_TEST and LOG.is_enabled:
            handle_request_test(self, self.server.netflix_session, func_name, data)
        else:
            self.send_error(404, 'Not found')
            self.end_headers()

    def log_message(self, *args):  # pylint: disable=arguments-differ
        """Disable the BaseHTTPServer Log"""


class NFThreadedTCPServer(ThreadingMixIn, TCPServer):
    """Handle each request in a separate thread"""
    def __init__(self, server_address):
        ThreadingMixIn.__init__(self)
        TCPServer.__init__(self, server_address, NetflixHttpRequestHandler)
        # Define shared members
        self.netflix_session = NetflixSession()

    def __del__(self):
        if self.netflix_session.nfsession.session:
            # Close the connection pool of the session
            self.netflix_session.nfsession.session.close()


def handle_msl_request(server, func_name, data, params=None):
    if func_name == 'get_license':
        # Proxy for InputStream Adaptive to get the licence for the requested video
        license_data = server.server.netflix_session.msl_handler.get_license(data)
        server.send_response(200)
        server.end_headers()
        server.wfile.write(license_data)
    elif func_name == 'get_manifest':
        # Proxy for InputStream Adaptive to get the XML manifest for the requested video
        videoid = int(params['videoid'][0])
        challenge = server.headers.get('challengeB64')
        sid = server.headers.get('sessionId')
        if not challenge or not sid:
            from xbmcaddon import Addon
            isa_version = remove_ver_suffix(Addon('inputstream.adaptive').getAddonInfo('version'))
            if common.CmpVersion(isa_version) >= '2.6.18':
                raise Exception(f'Widevine session data not valid\r\nSession ID: {sid} Challenge: {challenge}')
            # TODO: We temporary allow the use of older versions of InputStream Adaptive (but SD video content)
            #       to allow a soft transition, this must be removed in future.
            LOG.error('Detected older version of InputStream Adaptive add-on, HD video contents are not supported.')
            challenge = ''
            sid = ''
        manifest_data = server.server.netflix_session.msl_handler.get_manifest(videoid, unquote(challenge), sid)
        server.send_response(200)
        server.send_header('Content-type', 'application/xml')
        server.end_headers()
        server.wfile.write(manifest_data)
    else:
        handle_request(server, server.server.netflix_session, func_name, data)


def handle_request(server, handler, func_name, data):
    server.send_response(200)
    server.end_headers()
    try:
        try:
            func = handler.http_ipc_slots[func_name]
        except KeyError as exc:
            raise SlotNotImplemented(f'The specified IPC slot {func_name} does not exist') from exc
        ret_data = _call_func(func, pickle.loads(data))
    except Exception as exc:  # pylint: disable=broad-except
        if not isinstance(exc, (CacheMiss, MetadataNotAvailable)):
            LOG.error('IPC callback raised exception: {exc}', exc=exc)
            import traceback
            LOG.error(traceback.format_exc())
        ret_data = exc
    if ret_data:
        server.wfile.write(pickle.dumps(ret_data, protocol=pickle.HIGHEST_PROTOCOL))


def handle_cache_request(server, func_name, data):
    server.send_response(200)
    server.end_headers()
    try:
        ret_data = _call_instance_func(G.CACHE_MANAGEMENT, func_name, pickle.loads(data))
    except Exception as exc:  # pylint: disable=broad-except
        if not isinstance(exc, (CacheMiss, MetadataNotAvailable)):
            LOG.error('IPC callback raised exception: {exc}', exc=exc)
            import traceback
            LOG.error(traceback.format_exc())
        ret_data = exc
    if ret_data:
        server.wfile.write(pickle.dumps(ret_data, protocol=pickle.HIGHEST_PROTOCOL))


def handle_request_test(server, handler, func_name, data):
    server.send_response(200)
    server.end_headers()
    import json
    try:
        try:
            func = handler.http_ipc_slots[func_name]
        except KeyError as exc:
            raise SlotNotImplemented(f'The specified IPC slot {func_name} does not exist') from exc
        ret_data = _call_func(func, json.loads(data))
    except Exception as exc:  # pylint: disable=broad-except
        ret_data = f'The request has failed, error: {exc}'
    if ret_data:
        server.wfile.write(json.dumps(ret_data).encode('utf-8'))


def _call_instance_func(instance, func_name, data):
    try:
        func = getattr(instance, func_name)
    except AttributeError as exc:
        raise InvalidPathError(f'Function {func_name} not found') from exc
    if isinstance(data, dict):
        return func(**data)
    if data is not None:
        return func(data)
    return func()


def _call_func(func, data):
    if isinstance(data, dict):
        return func(**data)
    if data is not None:
        return func(data)
    return func()
