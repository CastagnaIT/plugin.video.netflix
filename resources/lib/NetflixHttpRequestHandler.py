# pylint: skip-file
# -*- coding: utf-8 -*-
# Module: NetflixHttpRequestHandler
# Created on: 07.03.2017

"""Oppionionated internal proxy that dispatches requests to Netflix"""

import json
import BaseHTTPServer
from types import FunctionType
from urlparse import urlparse, parse_qs
from utils import get_class_methods
from KodiHelper import KodiHelper
from NetflixSession import NetflixSession
from NetflixHttpSubRessourceHandler import NetflixHttpSubRessourceHandler

KODI_HELPER = KodiHelper()
NETFLIX_SESSION = NetflixSession(
    cookie_path=KODI_HELPER.cookie_path,
    data_path=KODI_HELPER.data_path,
    verify_ssl=KODI_HELPER.get_ssl_verification_setting(),
    log_fn=KODI_HELPER.log
)

# get list of methods & instance form the sub ressource handler
METHODS = get_class_methods(class_item=NetflixHttpSubRessourceHandler)
RES_HANDLER = NetflixHttpSubRessourceHandler(
    kodi_helper=KODI_HELPER,
    netflix_session=NETFLIX_SESSION)


class NetflixHttpRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    """Oppionionated internal proxy that dispatches requests to Netflix"""

    def do_GET(self):
        """
        GET request handler
        (we only need this, as we only do GET requests internally)
        """
        url = urlparse(self.path)
        params = parse_qs(url.query)
        method = params.get('method', [None])[0]

        # not method given
        if method is None:
            self.send_error(500, 'No method declared')
            return

        # no existing method given
        if method not in METHODS:
            error_msg = 'Method "'
            error_msg += str(method)
            error_msg += '" not found. Available methods: '
            error_msg += str(methods)
            return self.send_error(404, error_msg)

        # call method & get the result
        result = getattr(RES_HANDLER, method)(params)
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        return self.wfile.write(json.dumps({
            'method': method,
            'result': result}))

    def log_message(self, format, *args):
        """Disable the BaseHTTPServer Log"""
        return
