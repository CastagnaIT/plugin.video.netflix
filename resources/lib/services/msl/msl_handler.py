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
    @common.time_execution(immediate=True)
    def perform_key_handshake(self, data=None):
        """Perform a key handshake and initialize crypto keys"""
        # pylint: disable=unused-argument
        esn = data or g.get_esn()
        if not esn:
            common.info('Cannot perform key handshake, missing ESN')
            return

        common.debug('Performing key handshake. ESN: {}'.format(esn))

        response = _process_json_response(
            self._post(ENDPOINTS['chrome']['manifest'],
                       self.request_builder.handshake_request(esn)))
        headerdata = json.loads(
            base64.standard_b64decode(response['headerdata']))
        self.request_builder.crypto.parse_key_response(
            headerdata, not esn.startswith('NFCDIE-02-'))
        common.debug('Key handshake successful')

    @display_error_info
    @common.time_execution(immediate=True)
    def load_manifest(self, viewable_id):
        """
        Loads the manifets for the given viewable_id and
        returns a mpd-XML-Manifest

        :param viewable_id: The id of of the viewable
        :return: MPD XML Manifest or False if no success
        """
        manifest = self._load_manifest(viewable_id, g.get_esn())
        if not has_1080p(manifest):
            common.debug('Manifest has no 1080p viewables')
            manifest = self.get_edge_manifest(viewable_id, manifest)
        return self.__tranform_to_dash(manifest)

    def get_edge_manifest(self, viewable_id, chrome_manifest):
        """Load a manifest with an EDGE ESN and replace playback_context and
        drm_context"""
        common.debug('Loading EDGE manifest')
        esn = generate_edge_esn()
        common.debug('Switching MSL data to EDGE')
        self.perform_key_handshake(esn)
        manifest = self._load_manifest(viewable_id, esn)
        manifest['playbackContextId'] = chrome_manifest['playbackContextId']
        manifest['drmContextId'] = chrome_manifest['drmContextId']
        common.debug('Successfully loaded EDGE manifest')
        common.debug('Resetting MSL data to Chrome')
        self.perform_key_handshake()
        return manifest

    @common.time_execution(immediate=True)
    def _load_manifest(self, viewable_id, esn):
        common.debug('Requesting manifest for {} with ESN {}'
                     .format(viewable_id, esn))
        manifest_request_data = {
            'method': 'manifest',
            'lookupType': 'STANDARD',
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
            'flavor': 'STANDARD',
            'secureUrls': False,
            'supportPreviewContent': True,
            'forceClearStreams': False,
            'languages': ['de-DE'],
            'clientVersion': '4.0004.899.011',
            'uiVersion': 'akira'
        }
        manifest = self._chunked_request(ENDPOINTS['chrome']['manifest'],
                                         manifest_request_data, esn)
        common.save_file('manifest.json', json.dumps(manifest))
        return manifest['result']['viewables'][0]

    @display_error_info
    @common.time_execution(immediate=True)
    def get_license(self, challenge, sid):
        """
        Requests and returns a license for the given challenge and sid
        :param challenge: The base64 encoded challenge
        :param sid: The sid paired to the challengew
        :return: Base64 representation of the licensekey or False unsuccessfull
        """
        common.debug('Requesting license')
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
                                         license_request_data, g.get_esn())
        common.debug(response)
        return response['result']['licenses'][0]['data']

    @common.time_execution(immediate=True)
    def __tranform_to_dash(self, manifest):
        self.last_playback_context = manifest['playbackContextId']
        self.last_drm_context = manifest['drmContextId']
        return convert_to_dash(manifest)

    @common.time_execution(immediate=True)
    def _chunked_request(self, endpoint, request_data, esn):
        """Do a POST request and process the chunked response"""
        return self._process_chunked_response(
            self._post(endpoint,
                       self.request_builder.msl_request(request_data, esn)))

    @common.time_execution(immediate=True)
    def _post(self, endpoint, request_data):
        """Execute a post request"""
        common.debug('Executing POST request to {}'.format(endpoint))
        start = time.clock()
        response = self.session.post(endpoint, request_data)
        common.debug('Request took {}s'.format(time.clock() - start))
        common.debug('Request returned response with status {}'
                     .format(response.status_code))
        response.raise_for_status()
        return response

    @common.time_execution(immediate=True)
    def _process_chunked_response(self, response):
        """Parse and decrypt an encrypted chunked response. Raise an error
        if the response is plaintext json"""
        try:
            # if the json() does not fail we have an error because
            # the expected response is a chunked json response
            return _raise_if_error(response.json())
        except ValueError:
            # json() failed so parse and decrypt the chunked response
            common.debug('Received encrypted chunked response')
            response = _parse_chunks(response.text)
            return _decrypt_chunks(response['payloads'],
                                   self.request_builder.crypto)


@common.time_execution(immediate=True)
def _process_json_response(response):
    """Execute a post request and expect a JSON response"""
    try:
        return _raise_if_error(response.json())
    except ValueError:
        raise MSLError('Expected JSON response, got {}'.format(response.text))


def _raise_if_error(decoded_response):
    if ('errordata' in decoded_response or
            'errorDisplayMessage' in decoded_response.get('result', {}) or
            not decoded_response.get('success', True)):
        raise MSLError(_get_error_details(decoded_response))
    return decoded_response


def _get_error_details(decoded_response):
    if 'errordata' in decoded_response:
        return json.loads(
            base64.standard_b64decode(
                decoded_response['errordata']))['errormsg']
    elif 'errorDisplayMessage' in decoded_response.get('result', {}):
        return decoded_response['result']['errorDisplayMessage']

    common.error('Received an unknown error from MSL endpoint:\n{}'
                 .format(json.dumps(decoded_response)))
    return ''


@common.time_execution(immediate=True)
def _parse_chunks(message):
    header = message.split('}}')[0] + '}}'
    payloads = re.split(',\"signature\":\"[0-9A-Za-z=/+]+\"}',
                        message.split('}}')[1])
    payloads = [x + '}' for x in payloads][:-1]
    return {'header': header, 'payloads': payloads}


@common.time_execution(immediate=True)
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


def has_1080p(manifest):
    """Return True if any of the video tracks in manifest have a 1080p profile
    available, else False"""
    return any(video['contentProfile'] == 'playready-h264mpl40-dash'
               for video in manifest['videoTracks'][0]['downloadables'])


def generate_edge_esn():
    """Generate a random EDGE ESN"""
    import random
    esn = ['NFCDIE-02-']
    possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    for _ in range(0, 30):
        esn.append(random.choice(possible))
    return''.join(esn)
