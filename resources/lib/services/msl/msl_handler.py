# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2017 Trummerjo (original implementation module)
    Proxy service to convert manifest, provide license data and handle events

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import json
import time

import xbmcaddon

import resources.lib.common as common
from resources.lib.api.exceptions import CacheMiss
from resources.lib.common.cache_utils import CACHE_MANIFESTS
from resources.lib.database.db_utils import TABLE_SESSION
from resources.lib.globals import g
from .converter import convert_to_dash
from .events_handler import EventsHandler
from .exceptions import MSLError
from .msl_requests import MSLRequests
from .msl_utils import ENDPOINTS, display_error_info, MSL_DATA_FILENAME
from .profiles import enabled_profiles

try:  # Python 2
    unicode
except NameError:  # Python 3
    unicode = str  # pylint: disable=redefined-builtin


class MSLHandler(object):
    """Handles session management and crypto for license, manifest and event requests"""
    last_license_url = ''
    licenses_session_id = []
    licenses_xid = []
    licenses_release_url = []

    def __init__(self):
        super(MSLHandler, self).__init__()
        self._events_handler_thread = None
        self._init_msl_handler()
        common.register_slot(
            signal=common.Signals.ESN_CHANGED,
            callback=self.msl_requests.perform_key_handshake)
        common.register_slot(
            signal=common.Signals.RELEASE_LICENSE,
            callback=self.release_license)
        common.register_slot(
            signal=common.Signals.CLEAR_USER_ID_TOKENS,
            callback=self.clear_user_id_tokens)
        common.register_slot(
            signal=common.Signals.REINITIALIZE_MSL_HANDLER,
            callback=self.reinitialize_msl_handler)
        common.register_slot(
            signal=common.Signals.SWITCH_EVENTS_HANDLER,
            callback=self.switch_events_handler)

    def _init_msl_handler(self):
        self.msl_requests = None
        try:
            msl_data = json.loads(common.load_file(MSL_DATA_FILENAME))
            common.info('Loaded MSL data from disk')
        except Exception:  # pylint: disable=broad-except
            msl_data = None
        self.msl_requests = MSLRequests(msl_data)
        self.switch_events_handler()

    def reinitialize_msl_handler(self, data=None):  # pylint: disable=unused-argument
        """
        Reinitialize the MSL handler
        :param data: set True for delete the msl file data, and then reset all
        """
        common.debug('Reinitializing MSL handler')
        if data is True:
            common.delete_file(MSL_DATA_FILENAME)
        self._init_msl_handler()

    def switch_events_handler(self, data=None):
        """Switch to enable or disable the Events handler"""
        if self._events_handler_thread:
            self._events_handler_thread.stop_join()
            self._events_handler_thread = None
        if g.ADDON.getSettingBool('ProgressManager_enabled') or data:
            self._events_handler_thread = EventsHandler(self.msl_requests.chunked_request)
            self._events_handler_thread.start()

    @display_error_info
    @common.time_execution(immediate=True)
    def load_manifest(self, viewable_id):
        """
        Loads the manifests for the given viewable_id and returns a mpd-XML-Manifest

        :param viewable_id: The id of of the viewable
        :return: MPD XML Manifest or False if no success
        """
        try:
            manifest = self._load_manifest(viewable_id, g.get_esn())
        except MSLError as exc:
            if 'Email or password is incorrect' in str(exc):
                # Known cases when MSL error "Email or password is incorrect." can happen:
                # - If user change the password when the nf session was still active
                # - Netflix has reset the password for suspicious activity when the nf session was still active
                # Then clear the credentials and also user tokens.
                common.purge_credentials()
                self.msl_requests.crypto.clear_user_id_tokens()
            raise
        # Disable 1080p Unlock for now, as it is broken due to Netflix changes
        # if (g.ADDON.getSettingBool('enable_1080p_unlock') and
        #         not g.ADDON.getSettingBool('enable_vp9_profiles') and
        #         not has_1080p(manifest)):
        #     common.debug('Manifest has no 1080p viewables, trying unlock')
        #     manifest = self.get_edge_manifest(viewable_id, manifest)
        return self.__tranform_to_dash(manifest)

    def get_edge_manifest(self, viewable_id, chrome_manifest):
        """Load a manifest with an EDGE ESN and replace playback_context and drm_context"""
        common.debug('Loading EDGE manifest')
        esn = g.get_edge_esn()
        common.debug('Switching MSL data to EDGE')
        self.msl_requests.perform_key_handshake(esn)
        manifest = self._load_manifest(viewable_id, esn)
        manifest['playbackContextId'] = chrome_manifest['playbackContextId']
        manifest['drmContextId'] = chrome_manifest['drmContextId']
        common.debug('Successfully loaded EDGE manifest')
        common.debug('Resetting MSL data to Chrome')
        self.msl_requests.perform_key_handshake()
        return manifest

    @common.time_execution(immediate=True)
    def _load_manifest(self, viewable_id, esn):
        cache_identifier = esn + '_' + unicode(viewable_id)
        try:
            # The manifest must be requested once and maintained for its entire duration
            manifest = g.CACHE.get(CACHE_MANIFESTS, cache_identifier)
            expiration = int(manifest['expiration'] / 1000)
            if (expiration - time.time()) < 14400:
                # Some devices remain active even longer than 48 hours, if the manifest is at the limit of the deadline
                # when requested by am_stream_continuity.py / events_handler.py will cause problems
                # if it is already expired, so we guarantee a minimum of safety ttl of 4h (14400s = 4 hours)
                raise CacheMiss()
            if common.is_debug_verbose():
                common.debug('Manifest for {} obtained from the cache', viewable_id)
                # Save the manifest to disk as reference
                common.save_file('manifest.json', json.dumps(manifest).encode('utf-8'))
            return manifest
        except CacheMiss:
            pass

        isa_addon = xbmcaddon.Addon('inputstream.adaptive')
        hdcp_override = isa_addon is not None and isa_addon.getSettingBool('HDCPOVERRIDE')
        hdcp_4k_capable = common.is_device_4k_capable() or g.ADDON.getSettingBool('enable_force_hdcp')

        hdcp_version = []
        if not hdcp_4k_capable and hdcp_override:
            hdcp_version = ['1.4']
        if hdcp_4k_capable and hdcp_override:
            hdcp_version = ['2.2']

        common.info('Requesting manifest for {} with ESN {} and HDCP {}',
                    viewable_id,
                    common.censure(esn) if g.ADDON.getSetting('esn') else esn,
                    hdcp_version)

        profiles = enabled_profiles()
        from pprint import pformat
        common.info('Requested profiles:\n{}', pformat(profiles, indent=2))

        params = {
            'type': 'standard',
            'viewableId': [viewable_id],
            'profiles': profiles,
            'flavor': 'PRE_FETCH',
            'drmType': 'widevine',
            'drmVersion': 25,
            'usePsshBox': True,
            'isBranching': False,
            'isNonMember': False,
            'isUIAutoPlay': False,
            'useHttpsStreams': True,
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
                'isHdcpEngaged': hdcp_override
            }],
            'preferAssistiveAudio': False
        }

        manifest = self.msl_requests.chunked_request(ENDPOINTS['manifest'],
                                                     self.msl_requests.build_request_data('/manifest', params),
                                                     esn,
                                                     disable_msl_switch=False)
        if common.is_debug_verbose():
            # Save the manifest to disk as reference
            common.save_file('manifest.json', json.dumps(manifest).encode('utf-8'))
        # Save the manifest to the cache to retrieve it during its validity
        expiration = int(manifest['expiration'] / 1000)
        g.CACHE.add(CACHE_MANIFESTS, cache_identifier, manifest, expires=expiration)
        if 'result' in manifest:
            return manifest['result']
        return manifest

    @display_error_info
    @common.time_execution(immediate=True)
    def get_license(self, challenge, sid):
        """
        Requests and returns a license for the given challenge and sid

        :param challenge: The base64 encoded challenge
        :param sid: The sid paired to the challenge
        :return: Base64 representation of the license key or False unsuccessful
        """
        common.debug('Requesting license')

        timestamp = int(time.time() * 10000)
        xid = str(timestamp + 1610)
        params = [{
            'drmSessionId': sid,
            'clientTime': int(timestamp / 10000),
            'challengeBase64': challenge,
            'xid': xid
        }]
        response = self.msl_requests.chunked_request(ENDPOINTS['license'],
                                                     self.msl_requests.build_request_data(self.last_license_url,
                                                                                          params,
                                                                                          'drmSessionId'),
                                                     g.get_esn())
        # This xid must be used also for each future Event request, until playback stops
        g.LOCAL_DB.set_value('xid', xid, TABLE_SESSION)

        self.licenses_xid.insert(0, xid)
        self.licenses_session_id.insert(0, sid)
        self.licenses_release_url.insert(0, response[0]['links']['releaseLicense']['href'])

        if self.msl_requests.msl_switch_requested:
            self.msl_requests.msl_switch_requested = False
            self.bind_events()
        return response[0]['licenseResponseBase64']

    def bind_events(self):
        """Bind events"""
        # I don't know the real purpose of its use, it seems to be requested after the license and before starting
        # playback, and only the first time after a switch,
        # in the response you can also understand if the msl switch has worked
        common.debug('Requesting bind events')
        response = self.msl_requests.chunked_request(ENDPOINTS['events'],
                                                     self.msl_requests.build_request_data('/bind', {}),
                                                     g.get_esn(),
                                                     disable_msl_switch=False)
        common.debug('Bind events response: {}', response)

    @display_error_info
    @common.time_execution(immediate=True)
    def release_license(self, data=None):  # pylint: disable=unused-argument
        """Release the server license"""
        try:
            # When UpNext is used a new video is loaded while another one is running and not yet released,
            # so you need to take the right data of first added license
            url = self.licenses_release_url.pop()
            sid = self.licenses_session_id.pop()
            xid = self.licenses_xid.pop()

            common.debug('Requesting releasing license')
            params = [{
                'url': url,
                'params': {
                    'drmSessionId': sid,
                    'xid': xid
                },
                'echo': 'drmSessionId'
            }]

            response = self.msl_requests.chunked_request(ENDPOINTS['license'],
                                                         self.msl_requests.build_request_data('/bundle', params),
                                                         g.get_esn())
            common.debug('License release response: {}', response)
        except IndexError:
            # Example the supplemental media type have no license
            common.debug('No license to release')

    def clear_user_id_tokens(self, data=None):  # pylint: disable=unused-argument
        """Clear all user id tokens"""
        self.msl_requests.crypto.clear_user_id_tokens()

    @common.time_execution(immediate=True)
    def __tranform_to_dash(self, manifest):
        self.last_license_url = manifest['links']['license']['href']
        return convert_to_dash(manifest)


def has_1080p(manifest):
    """Return True if any of the video tracks in manifest have a 1080p profile available, else False"""
    return any(video['width'] >= 1920
               for video in manifest['videoTracks'][0]['downloadables'])
