# -*- coding: utf-8 -*-
# Author: trummerjo
# Module: MSLHttpRequestHandler
# Created on: 26.01.2017
# License: MIT https://goo.gl/5bMj3H
"""Proxy service to convert manifest and provide license data"""
from __future__ import unicode_literals

import re
import zlib
import json
import time
import base64
from functools import wraps
import requests

from resources.lib.globals import g
import resources.lib.common as common
import resources.lib.kodi.ui as ui

from .request_builder import MSLRequestBuilder
from .profiles import enabled_profiles
from .converter import convert_to_dash
from .exceptions import MSLError

CHROME_BASE_URL = 'http://www.netflix.com/api/msl/NFCDCH-LX/cadmium/'
ENDPOINTS = {
    'chrome': {
        'manifest': CHROME_BASE_URL + 'manifest',
        'license': CHROME_BASE_URL + 'license'},
    'edge': {
        'manifest': None,
        'license': None}
}


def display_error_info(func):
    """Decorator that catches errors raise by the decorated function,
    displays an error info dialog in the UI and reraises the error"""
    # pylint: disable=missing-docstring
    @wraps(func)
    def error_catching_wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            import traceback
            common.error(traceback.format_exc())
            ui.show_error_info(common.get_local_string(30028), exc.message,
                               unknown_error=not exc.message)
            raise
    return error_catching_wrapper


class MSLHandler(object):
    """Handles session management and crypto for license and manifest
    requests"""
    last_drm_context = ''
    last_playback_context = ''
    session = requests.session()

    def __init__(self):
        # pylint: disable=broad-except
        try:
            msl_data = json.loads(common.load_file('msl_data.json'))
            self.request_builder = MSLRequestBuilder(msl_data)
            common.debug('Loaded MSL data from disk')
        except Exception:
            import traceback
            common.debug(traceback.format_exc())
            common.debug('Stored MSL data expired or not available')
            self.request_builder = MSLRequestBuilder()
            self.perform_key_handshake()
        common.register_slot(
            signal=common.Signals.ESN_CHANGED,
            callback=self.perform_key_handshake)

    @display_error_info
    def perform_key_handshake(self):
        """Perform a key handshake and initialize crypto keys"""
        if not g.get_esn():
            common.error('Cannot perform key handshake, missing ESN')
            return

        common.debug('Performing key handshake. ESN: {}'.format(g.get_esn()))

        response = _process_json_response(
            self._post(ENDPOINTS['chrome']['manifest'],
                       self.request_builder.handshake_request()))
        headerdata = json.loads(
            base64.standard_b64decode(response['headerdata']))
        self.request_builder.crypto.parse_key_response(headerdata)
        common.debug('Key handshake successful')

    @display_error_info
    def load_manifest(self, viewable_id):
        """
        Loads the manifets for the given viewable_id and
        returns a mpd-XML-Manifest

        :param viewable_id: The id of of the viewable
        :return: MPD XML Manifest or False if no success
        """
        manifest_request_data = {
            'method': 'manifest',
            'lookupType': 'PREPARE',
            'viewableIds': [viewable_id],
            'profiles': enabled_profiles(),
            'drmSystem': 'widevine',
            'appId': '14673889385265',
            'sessionParams': {
                'pinCapableClient': False,
                'uiplaycontext': 'null'
            },
            'sessionId': '14673889385265',
            'trackId': 0,
            'flavor': 'PRE_FETCH',
            'secureUrls': False,
            'supportPreviewContent': True,
            'forceClearStreams': False,
            'languages': ['de-DE'],
            'clientVersion': '4.0004.899.011',
            'uiVersion': 'akira'
        }
        manifest = self._chunked_request(ENDPOINTS['chrome']['manifest'],
                                         manifest_request_data)
        return self.__tranform_to_dash(manifest)

    @display_error_info
    def get_license(self, challenge, sid):
        """
        Requests and returns a license for the given challenge and sid
        :param challenge: The base64 encoded challenge
        :param sid: The sid paired to the challengew
        :return: Base64 representation of the licensekey or False unsuccessfull
        """
        license_request_data = {
            'method': 'license',
            'licenseType': 'STANDARD',
            'clientVersion': '4.0004.899.011',
            'uiVersion': 'akira',
            'languages': ['de-DE'],
            'playbackContextId': self.last_playback_context,
            'drmContextIds': [self.last_drm_context],
            'challenges': [{
                'dataBase64': challenge,
                'sessionId': sid
            }],
            'clientTime': int(time.time()),
            'xid': int((int(time.time()) + 0.1612) * 1000)

        }
        response = self._chunked_request(ENDPOINTS['chrome']['license'],
                                         license_request_data)
        return response['result']['licenses'][0]['data']

    def __tranform_to_dash(self, manifest):
        common.save_file('manifest.json', json.dumps(manifest))
        manifest = manifest['result']['viewables'][0]
        self.last_playback_context = manifest['playbackContextId']
        self.last_drm_context = manifest['drmContextId']
        return convert_to_dash(manifest)

    def _chunked_request(self, endpoint, request_data):
        """Do a POST request and process the chunked response"""
        return self._process_chunked_response(
            self._post(endpoint,
                       self.request_builder.msl_request(request_data)))

    def _post(self, endpoint, request_data):
        """Execute a post request"""
        response = self.session.post(endpoint, request_data)
        response.raise_for_status()
        return response

    def _process_chunked_response(self, response):
        """Parse and decrypt an encrypted chunked response. Raise an error
        if the response is plaintext json"""
        try:
            # if the json() does not fail we have an error because
            # the expected response is a chunked json response
            return _raise_if_error(json.loads(response))
        except ValueError:
            import traceback
            common.debug(traceback.format_exc())
            # json() failed so parse and decrypt the chunked response
            response = _parse_chunks(response.text)
            return _decrypt_chunks(response['payloads'],
                                   self.request_builder.crypto)


def _process_json_response(response):
    """Execute a post request and expect a JSON response"""
    try:
        return _raise_if_error(response.json())
    except ValueError:
        raise MSLError('Expected JSON response, got {}'.format(response.text))


def _raise_if_error(decoded_response):
    if 'errordata' in decoded_response or not decoded_response['success']:
        raise MSLError(_get_error_details(decoded_response))
    return decoded_response


def _get_error_details(decoded_response):
    if 'errordata' in decoded_response:
        return json.loads(
            base64.standard_b64decode(
                decoded_response['errordata']))['errormsg']
    elif 'errorDisplayMessage' in decoded_response['result']:
        return decoded_response['result']['errorDisplayMessage']

    common.error('Received an unknown error from MSL endpoint:\n{}'
                 .format(json.dumps(decoded_response)))
    return ''


def _parse_chunks(message):
    header = message.split('}}')[0] + '}}'
    payloads = re.split(',\"signature\":\"[0-9A-Za-z=/+]+\"}',
                        message.split('}}')[1])
    payloads = [x + '}' for x in payloads][:-1]
    return {'header': header, 'payloads': payloads}


def _decrypt_chunks(chunks, crypto):
    decrypted_payload = ''
    for chunk in chunks:
        payloadchunk = json.loads(chunk)
        payload = payloadchunk.get('payload')
        decoded_payload = base64.standard_b64decode(payload)
        encryption_envelope = json.loads(decoded_payload)
        # Decrypt the text
        plaintext = crypto.decrypt(
            base64.standard_b64decode(encryption_envelope['iv']),
            base64.standard_b64decode(encryption_envelope.get('ciphertext')))
        # unpad the plaintext
        plaintext = json.loads(plaintext)
        data = plaintext.get('data')

        # uncompress data if compressed
        if plaintext.get('compressionalgo') == 'GZIP':
            decoded_data = base64.standard_b64decode(data)
            data = zlib.decompress(decoded_data, 16 + zlib.MAX_WBITS)
        else:
            data = base64.standard_b64decode(data)
        decrypted_payload += data

    decrypted_payload = json.loads(decrypted_payload)[1]['payload']['data']
    decrypted_payload = base64.standard_b64decode(decrypted_payload)
    return json.loads(decrypted_payload)
