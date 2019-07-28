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
import xbmcaddon

from resources.lib.database.db_utils import (TABLE_SESSION)
from resources.lib.globals import g
import resources.lib.common as common
import resources.lib.kodi.ui as ui

from .request_builder import MSLRequestBuilder
from .profiles import enabled_profiles
from .converter import convert_to_dash
from .exceptions import MSLError

CHROME_BASE_URL = 'https://www.netflix.com/nq/msl_v1/cadmium/'
ENDPOINTS = {
    'manifest': CHROME_BASE_URL + 'pbo_manifests/%5E1.0.0/router',  # "pbo_manifests/^1.0.0/router"
    'license': CHROME_BASE_URL + 'pbo_licenses/%5E1.0.0/router'
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
            ui.show_error_info(common.get_local_string(30028), unicode(exc.message),
                               unknown_error=not exc.message,
                               netflix_error=isinstance(exc, MSLError))
            raise
    return error_catching_wrapper


class MSLHandler(object):
    """Handles session management and crypto for license and manifest
    requests"""
    last_license_url = ''
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
            if self.perform_key_handshake():
                self.request_builder = MSLRequestBuilder(json.loads(
                    common.load_file('msl_data.json')))
                common.debug('Loaded renewed MSL data from disk')
        common.register_slot(
            signal=common.Signals.ESN_CHANGED,
            callback=self.perform_key_handshake)

    @display_error_info
    @common.time_execution(immediate=True)
    def perform_key_handshake(self, data=None):
        """Perform a key handshake and initialize crypto keys"""
        # pylint: disable=unused-argument
        esn = data or g.LOCAL_DB.get_value('esn', table=TABLE_SESSION)
        if not esn:
            common.info('Cannot perform key handshake, missing ESN')
            return False

        common.debug('Performing key handshake. ESN: {}'.format(esn))

        response = _process_json_response(
            self._post(ENDPOINTS['manifest'],
                       self.request_builder.handshake_request(esn)))
        headerdata = json.loads(
            base64.standard_b64decode(response['headerdata']))
        self.request_builder.crypto.parse_key_response(
            headerdata, not common.is_edge_esn(esn))
        common.debug('Key handshake successful')
        return True

    @display_error_info
    @common.time_execution(immediate=True)
    def load_manifest(self, viewable_id):
        """
        Loads the manifets for the given viewable_id and
        returns a mpd-XML-Manifest

        :param viewable_id: The id of of the viewable
        :return: MPD XML Manifest or False if no success
        """
        manifest = self._load_manifest(viewable_id, g.LOCAL_DB.get_value('esn', table=TABLE_SESSION))
        # Disable 1080p Unlock for now, as it is broken due to Netflix changes
        # if (g.ADDON.getSettingBool('enable_1080p_unlock') and
        #         not g.ADDON.getSettingBool('enable_vp9_profiles') and
        #         not has_1080p(manifest)):
        #     common.debug('Manifest has no 1080p viewables, trying unlock')
        #     manifest = self.get_edge_manifest(viewable_id, manifest)
        return self.__tranform_to_dash(manifest)

    def get_edge_manifest(self, viewable_id, chrome_manifest):
        """Load a manifest with an EDGE ESN and replace playback_context and
        drm_context"""
        common.debug('Loading EDGE manifest')
        esn = g.get_edge_esn()
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
        profiles = enabled_profiles()
        import pprint
        common.debug('Requested profiles:\n{}'
                     .format(pprint.pformat(profiles, indent=2)))

        ia_addon = xbmcaddon.Addon('inputstream.adaptive')
        hdcp = ia_addon is not None and ia_addon.getSetting('HDCPOVERRIDE') == 'true'

        # TODO: Future implementation when available,
        #       request the HDCP version from Kodi through a function
        #       in CryptoSession currently not implemented
        #       so there will be no more need to use the HDCPOVERRIDE = true

        hdcp_version = []
        if not g.ADDON.getSettingBool('enable_force_hdcp') and hdcp:
            hdcp_version = ['1.4']
        if g.ADDON.getSettingBool('enable_force_hdcp') and hdcp:
            hdcp_version = ['2.2']

        id = int(time.time() * 10000)
        manifest_request_data = {
            'version': 2,
            'url': '/manifest',
            'id': id,
            'esn': esn,
            'languages': [g.LOCAL_DB.get_value('locale_id')],
            'uiVersion': 'shakti-v5bca5cd3',
            'clientVersion': '6.0013.315.051',
            'params': {
                'type': 'standard',
                'viewableId': [viewable_id],
                'profiles': profiles,
                'flavor': 'PRE_FETCH',
                'drmType': 'widevine',
                'drmVersion': 25,
                'usePsshBox': True,
                'isBranching': False,
                'useHttpsStreams': False,
                'imageSubtitleHeight': 1080,
                'uiVersion': 'shakti-v5bca5cd3',
                'uiPlatform': 'SHAKTI',
                'clientVersion': '6.0013.315.051',
                'supportsPreReleasePin': True,
                'supportsWatermark': True,
                'showAllSubDubTracks': False,
                'titleSpecificData': {},
                'videoOutputInfo': [{
                    'type': 'DigitalVideoOutputDescriptor',
                    'outputType': 'unknown',
                    'supportedHdcpVersions': hdcp_version,
                    'isHdcpEngaged': hdcp
                }],
                'preferAssistiveAudio': False,
                'isNonMember': False
            }
        }

        manifest = self._chunked_request(ENDPOINTS['manifest'],
                                         manifest_request_data, esn)
        common.save_file('manifest.json', json.dumps(manifest))
        if 'result' in manifest:
            return manifest['result']
        return manifest

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
        id = int(time.time() * 10000)

        license_request_data = {
            'version': 2,
            'url': self.last_license_url,
            'id': id,
            'esn': g.LOCAL_DB.get_value('esn', table=TABLE_SESSION),
            'languages': [g.LOCAL_DB.get_value('locale_id')],
            'uiVersion': 'shakti-v5bca5cd3',
            'clientVersion': '6.0013.315.051',
            'params': [{
                'sessionId': sid,
                'clientTime': int(id / 10000),
                'challengeBase64': challenge,
                'xid': str(id + 1610)
            }],
            'echo': 'sessionId'
        }

        response = self._chunked_request(ENDPOINTS['license'],
                                         license_request_data,
                                         g.LOCAL_DB.get_value('esn', table=TABLE_SESSION))
        return response[0]['licenseResponseBase64']

    @common.time_execution(immediate=True)
    def __tranform_to_dash(self, manifest):
        self.last_license_url = manifest['links']['license']['href']
        self.last_playback_context = manifest['playbackContextId']
        self.last_drm_context = manifest['drmContextId']
        return convert_to_dash(manifest)

    @common.time_execution(immediate=True)
    def _chunked_request(self, endpoint, request_data, esn):
        """Do a POST request and process the chunked response"""
        chunked_response = self._process_chunked_response(
            self._post(endpoint, self.request_builder.msl_request(request_data, esn)))
        return chunked_response['result']

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
            decrypted_response = _decrypt_chunks(response['payloads'],
                                                 self.request_builder.crypto)
            return _raise_if_error(decrypted_response)


@common.time_execution(immediate=True)
def _process_json_response(response):
    """Execute a post request and expect a JSON response"""
    try:
        return _raise_if_error(response.json())
    except ValueError:
        raise MSLError('Expected JSON response, got {}'.format(response.text))


def _raise_if_error(decoded_response):
    if any(key in decoded_response for key in ['error', 'errordata']):
        common.error('Full MSL error information:')
        common.error(json.dumps(decoded_response))
        raise MSLError(_get_error_details(decoded_response))
    return decoded_response


def _get_error_details(decoded_response):
    if 'errordata' in decoded_response:
        return json.loads(
            base64.standard_b64decode(
                decoded_response['errordata']))['errormsg']
    if 'error' in decoded_response:
        if decoded_response['error'].get('errorDisplayMessage'):
            return decoded_response['error']['errorDisplayMessage']
    return 'Unhandled error check log.'


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

        if isinstance(data, str):
            decrypted_payload += unicode(data, 'utf-8')
        else:
            decrypted_payload += data

    return json.loads(decrypted_payload)


def has_1080p(manifest):
    """Return True if any of the video tracks in manifest have a 1080p profile
    available, else False"""
    return any(video['width'] >= 1920
               for video in manifest['videoTracks'][0]['downloadables'])
