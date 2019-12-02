# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2017 Trummerjo (original implementation module)
    Proxy service to convert manifest and provide license data

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import re
import zlib
import json
import time
import base64
from functools import wraps
import requests
import xbmcaddon

from resources.lib.globals import g
import resources.lib.common as common
import resources.lib.kodi.ui as ui
import resources.lib.cache as cache

from .request_builder import MSLRequestBuilder
from .profiles import enabled_profiles
from .converter import convert_to_dash
from .exceptions import MSLError

try:  # Python 2
    unicode
except NameError:  # Python 3
    unicode = str  # pylint: disable=redefined-builtin


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
            ui.show_error_info(common.get_local_string(30028), unicode(exc),
                               unknown_error=not(unicode(exc)),
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
        self.request_builder = None
        try:
            msl_data = json.loads(common.load_file('msl_data.json'))
            common.info('Loaded MSL data from disk')
        except Exception:
            msl_data = None
        try:
            self.request_builder = MSLRequestBuilder(msl_data)
            # Addon just installed, the service starts but there is no esn
            if g.get_esn():
                self.check_mastertoken_validity()
        except Exception:
            import traceback
            common.error(traceback.format_exc())
        common.register_slot(
            signal=common.Signals.ESN_CHANGED,
            callback=self.perform_key_handshake)

    def check_mastertoken_validity(self):
        """Return the mastertoken validity and executes a new key handshake when necessary"""
        if self.request_builder.crypto.mastertoken:
            time_now = time.time()
            renewable = self.request_builder.crypto.renewal_window < time_now
            expired = self.request_builder.crypto.expiration <= time_now
        else:
            renewable = False
            expired = True
        if expired:
            if not self.request_builder.crypto.mastertoken:
                common.debug('Stored MSL data not available, a new key handshake will be performed')
                self.request_builder = MSLRequestBuilder()
            else:
                common.debug('Stored MSL data is expired, a new key handshake will be performed')
            if self.perform_key_handshake():
                self.request_builder = MSLRequestBuilder(json.loads(
                    common.load_file('msl_data.json')))
            return self.check_mastertoken_validity()
        return {'renewable': renewable, 'expired': expired}

    @display_error_info
    @common.time_execution(immediate=True)
    def perform_key_handshake(self, data=None):
        """Perform a key handshake and initialize crypto keys"""
        # pylint: disable=unused-argument
        esn = data or g.get_esn()
        if not esn:
            common.info('Cannot perform key handshake, missing ESN')
            return False

        common.debug('Performing key handshake. ESN: {}', esn)

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
        manifest = self._load_manifest(viewable_id, g.get_esn())
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
        cache_identifier = esn + '_' + unicode(viewable_id)
        try:
            # The manifest must be requested once and maintained for its entire duration
            manifest = g.CACHE.get(cache.CACHE_MANIFESTS, cache_identifier, False)
            common.debug('Manifest for {} with ESN {} obtained from the cache', viewable_id, esn)
            # Save the manifest to disk as reference
            common.save_file('manifest.json', json.dumps(manifest).encode('utf-8'))
            return manifest
        except cache.CacheMiss:
            pass
        common.debug('Requesting manifest for {} with ESN {}', viewable_id, esn)
        profiles = enabled_profiles()
        import pprint
        common.info('Requested profiles:\n{}', pprint.pformat(profiles, indent=2))

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

        timestamp = int(time.time() * 10000)
        manifest_request_data = {
            'version': 2,
            'url': '/manifest',
            'id': timestamp,
            'languages': [g.LOCAL_DB.get_value('locale_id')],
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
                'uiVersion': 'shakti-v93016808',
                'uiPlatform': 'SHAKTI',
                'clientVersion': '6.0016.426.011',
                'desiredVmaf': 'plus_lts',  # phone_plus_exp can be used to mobile, not tested
                'supportsPreReleasePin': True,
                'supportsWatermark': True,
                'supportsUnequalizedDownloadables': True,
                'showAllSubDubTracks': False,
                'titleSpecificData': {
                    viewable_id: {
                        'unletterboxed': True
                    }
                },
                'videoOutputInfo': [{
                    'type': 'DigitalVideoOutputDescriptor',
                    'outputType': 'unknown',
                    'supportedHdcpVersions': hdcp_version,
                    'isHdcpEngaged': hdcp
                }],
                'preferAssistiveAudio': False,
                'isNonMember': False
            },
            'echo': ''
        }

        # Get and check mastertoken validity
        mt_validity = self.check_mastertoken_validity()
        manifest = self._chunked_request(ENDPOINTS['manifest'],
                                         manifest_request_data,
                                         esn,
                                         mt_validity)
        # Save the manifest to disk as reference
        common.save_file('manifest.json', json.dumps(manifest).encode('utf-8'))
        # Save the manifest to the cache to retrieve it during its validity
        expiration = int(manifest['expiration'] / 1000)
        g.CACHE.add(cache.CACHE_MANIFESTS, cache_identifier, manifest, eol=expiration)
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
        timestamp = int(time.time() * 10000)

        license_request_data = {
            'version': 2,
            'url': self.last_license_url,
            'id': timestamp,
            'languages': [g.LOCAL_DB.get_value('locale_id')],
            'params': [{
                'sessionId': sid,
                'clientTime': int(timestamp / 10000),
                'challengeBase64': challenge,
                'xid': str(timestamp + 1610)
            }],
            'echo': 'sessionId'
        }

        response = self._chunked_request(ENDPOINTS['license'], license_request_data, g.get_esn())
        return response[0]['licenseResponseBase64']

    @common.time_execution(immediate=True)
    def __tranform_to_dash(self, manifest):
        self.last_license_url = manifest['links']['license']['href']
        self.last_playback_context = manifest['playbackContextId']
        self.last_drm_context = manifest['drmContextId']
        return convert_to_dash(manifest)

    @common.time_execution(immediate=True)
    def _chunked_request(self, endpoint, request_data, esn, mt_validity=None):
        """Do a POST request and process the chunked response"""
        chunked_response = self._process_chunked_response(
            self._post(endpoint, self.request_builder.msl_request(request_data, esn)),
            mt_validity['renewable'] if mt_validity else None)
        return chunked_response['result']

    @common.time_execution(immediate=True)
    def _post(self, endpoint, request_data):
        """Execute a post request"""
        common.debug('Executing POST request to {}', endpoint)
        start = time.clock()
        response = self.session.post(endpoint, request_data)
        common.debug('Request took {}s', time.clock() - start)
        common.debug('Request returned response with status {}', response.status_code)
        response.raise_for_status()
        return response

    # pylint: disable=unused-argument
    @common.time_execution(immediate=True)
    def _process_chunked_response(self, response, mt_renewable):
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
            # TODO: sending for the renewal request is not yet implemented
            # if mt_renewable:
            #     # Check if mastertoken is renewed
            #     self.request_builder.crypto.compare_mastertoken(response['header']['mastertoken'])
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
    raise_error = False
    # Catch a manifest/chunk error
    if any(key in decoded_response for key in ['error', 'errordata']):
        raise_error = True
    # Catch a license error
    if 'result' in decoded_response and isinstance(decoded_response.get('result'), list):
        if 'error' in decoded_response['result'][0]:
            raise_error = True
    if raise_error:
        common.error('Full MSL error information:')
        common.error(json.dumps(decoded_response))
        raise MSLError(_get_error_details(decoded_response))
    return decoded_response


def _get_error_details(decoded_response):
    # Catch a chunk error
    if 'errordata' in decoded_response:
        return json.loads(
            base64.standard_b64decode(
                decoded_response['errordata']))['errormsg']
    # Catch a manifest error
    if 'error' in decoded_response:
        if decoded_response['error'].get('errorDisplayMessage'):
            return decoded_response['error']['errorDisplayMessage']
    # Catch a license error
    if 'result' in decoded_response and isinstance(decoded_response.get('result'), list):
        if 'error' in decoded_response['result'][0]:
            if decoded_response['result'][0]['error'].get('errorDisplayMessage'):
                return decoded_response['result'][0]['error']['errorDisplayMessage']
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
            data = zlib.decompress(decoded_data, 16 + zlib.MAX_WBITS).decode('utf-8')
        else:
            data = base64.standard_b64decode(data).decode('utf-8')

        decrypted_payload += data

    return json.loads(decrypted_payload)


def has_1080p(manifest):
    """Return True if any of the video tracks in manifest have a 1080p profile
    available, else False"""
    return any(video['width'] >= 1920
               for video in manifest['videoTracks'][0]['downloadables'])
