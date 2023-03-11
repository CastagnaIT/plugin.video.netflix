# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2017 Trummerjo (original implementation module)
    Proxy service to convert manifest, provide license data and handle events

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import base64
import json
import time
from typing import TYPE_CHECKING

import xbmcaddon

import resources.lib.common as common
from resources.lib.common.cache_utils import CACHE_MANIFESTS
from resources.lib.common.exceptions import MSLError
from resources.lib.database.db_utils import TABLE_SESSION
from resources.lib.globals import G
from resources.lib.utils.esn import get_esn, set_esn, regen_esn
from resources.lib.utils.logging import LOG, measure_exec_time_decorator
from .converter import convert_to_dash
from .events_handler import EventsHandler
from .msl_requests import MSLRequests
from .msl_utils import ENDPOINTS, display_error_info, MSL_DATA_FILENAME, create_req_params
from .profiles import enabled_profiles

if TYPE_CHECKING:  # This variable/imports are used only by the editor, so not at runtime
    from resources.lib.services.nfsession.nfsession_ops import NFSessionOperations


class MSLHandler:
    """Handles session management and crypto for license, manifest and event requests"""
    http_ipc_slots = {}
    last_license_url = ''
    licenses_session_id = []
    licenses_xid = []
    licenses_release_url = []
    licenses_response = None
    needs_license_request = True

    def __init__(self, nfsession: 'NFSessionOperations'):
        self.nfsession = nfsession
        self.events_handler_thread = None
        self._init_msl_handler()
        common.register_slot(
            signal=common.Signals.SWITCH_EVENTS_HANDLER,
            callback=self.switch_events_handler,
            is_signal=True)
        # Slot allocation for IPC
        self.slots = [self.msl_requests.perform_key_handshake]

    def _init_msl_handler(self):
        self.msl_requests = None
        try:
            msl_data = json.loads(common.load_file_def(MSL_DATA_FILENAME))
            LOG.info('Loaded MSL data from disk')
        except Exception:  # pylint: disable=broad-except
            msl_data = None
        self.msl_requests = MSLRequests(msl_data, self.nfsession)
        self.switch_events_handler()

    def reinitialize_msl_handler(self, delete_msl_file=False):
        """
        Reinitialize the MSL handler
        :param delete_msl_file: if True delete the msl file data
        """
        LOG.debug('Reinitializing MSL handler')
        if delete_msl_file:
            common.delete_file(MSL_DATA_FILENAME)
        self._init_msl_handler()

    def switch_events_handler(self, override_enable=False):
        """Switch to enable or disable the Events handler"""
        if self.events_handler_thread:
            self.events_handler_thread.stop_join()
            self.events_handler_thread = None
        if G.ADDON.getSettingBool('sync_watched_status') or override_enable:
            self.events_handler_thread = EventsHandler(self.msl_requests.chunked_request, self.nfsession)
            self.events_handler_thread.start()

    @display_error_info
    def get_manifest(self, viewable_id, challenge, sid):
        """
        Get the manifests for the given viewable_id and returns a mpd-XML-Manifest

        :param viewable_id: The id of of the viewable
        :return: MPD XML Manifest or False if no success
        """
        try:
            esn = get_esn()
            # When the add-on is installed from scratch or you logout the account the ESN will be empty
            if not esn:
                esn = set_esn()
            else:
                esn = regen_esn(esn)
            manifest = self._get_manifest(viewable_id, esn, challenge, sid)
        except MSLError as exc:
            if 'Email or password is incorrect' in str(exc):
                # Known cases when MSL error "Email or password is incorrect." can happen:
                # - If user change the password when the nf session was still active
                # - Netflix has reset the password for suspicious activity when the nf session was still active
                # Then clear the credentials and also user tokens.
                common.purge_credentials()
                self.msl_requests.crypto.clear_user_id_tokens()
            if 'User must login again' in str(exc):
                # Know case when MSL error can happen:
                # - User has done "Sign out of all devices" from account settings
                # - User has login with an auth key generated before executing "Sign out of all devices"
                # When "Sign out of all devices" is done, and you create a auth key just after that
                # for some reason the MSL has not yet changed his status and think you still use the old login
                # this is fixed automatically by website by waiting 10 minutes before generating a new auth key.
                err_msg = ('\nIf you have done "Sign out of all devices" from Netflix account settings so '
                           'Logout from add-on settings and wait about 10 minutes before login again '
                           '(if used, a new Auth Key is required).')
                raise MSLError(str(exc) + err_msg) from exc
            raise
        return self._tranform_to_dash(manifest)

    @measure_exec_time_decorator(is_immediate=True)
    def _get_manifest(self, viewable_id, esn, challenge, sid):
        if common.get_system_platform() != 'android' and (not challenge or not sid):
            LOG.error('DRM session data not valid (Session ID: {}, Challenge: {})', challenge, sid)

        from pprint import pformat

        isa_hdcp_override = False
        if G.KODI_VERSION < 20:
            isa_addon = xbmcaddon.Addon('inputstream.adaptive')
            isa_hdcp_override = isa_addon.getSettingBool('HDCPOVERRIDE')

        hdcp_level = None
        force_hdcp_level = G.ADDON.getSettingString('stream_force_hdcp')
        if force_hdcp_level != '--':
            hdcp_level = force_hdcp_level
        elif common.get_hdcp_level() >= 2.2:
            hdcp_level = '2.2'
        if not hdcp_level and isa_hdcp_override:
            hdcp_level = '1.4'

        # The manifest param 'supportedHdcpVersions' is set by hdcp_version
        # which can accept the following values: empty list, '1.4' and '2.2'
        hdcp_version = [hdcp_level] if hdcp_level else []

        manifest_ver = G.ADDON.getSettingString('msl_manifest_version')
        profiles = enabled_profiles()

        LOG.info('Requesting manifest (version {}) for\nVIDEO ID: {}\nESN: {}\nHDCP: {}\nPROFILES:\n{}',
                 manifest_ver,
                 viewable_id,
                 common.censure(esn) if len(esn) > 50 else esn,
                 hdcp_version,
                 pformat(profiles, indent=2))
        xid = int(time.time() * 10000)
        # On non-Android systems, we pre-initialize the DRM with default PSSH/KID, this allows to obtain Challenge/SID
        # to achieve 1080p resolution.
        # On Android, pre-initialize DRM is possible but cannot keep the same DRM session, will result in an error
        # because the manifest license data do not match the current DRM session, then we do not use it and
        # we still make the license requests.
        if manifest_ver == 'v1':
            endpoint_url, request_data = self._build_manifest_v1(viewable_id=viewable_id, hdcp_version=hdcp_version,
                                                                 profiles=profiles, challenge=challenge)
        else:  # Default - most recent version
            endpoint_url, request_data = self._build_manifest_v2(viewable_id=viewable_id, hdcp_version=hdcp_version,
                                                                 profiles=profiles, challenge=challenge,
                                                                 sid=sid, xid=xid)
        manifest = self.msl_requests.chunked_request(endpoint_url, request_data, esn)

        # The xid must be used also for each future MSL requests, until playback stops
        G.LOCAL_DB.set_value('xid', xid, TABLE_SESSION)

        if manifest_ver == 'default' and 'license' in manifest['video_tracks'][0]:
            self.needs_license_request = False
            self.licenses_xid.insert(0, xid)
            self.licenses_session_id.insert(0, manifest['video_tracks'][0]['license']['drmSessionId'])
            self.licenses_release_url.insert(0,
                                             manifest['video_tracks'][0]['license']['links']['releaseLicense']['href'])
            self.licenses_response = manifest['video_tracks'][0]['license']['licenseResponseBase64']
        else:
            self.needs_license_request = True

        self.last_license_url = manifest['links']['license']['href']

        if LOG.is_enabled:
            # Save the manifest to disk as reference
            common.save_file_def('manifest.json', json.dumps(manifest).encode('utf-8'))
        # Save the manifest to the cache, it will be used on am_video_events.py
        expiration = int(manifest['expiration'] / 1000)
        cache_identifier = f'{esn}_{viewable_id}'
        G.CACHE.add(CACHE_MANIFESTS, cache_identifier, manifest, expires=expiration)
        return manifest

    def _build_manifest_v1(self, **kwargs):
        params = {
            'type': 'standard',
            'viewableId': kwargs['viewable_id'],
            'profiles': kwargs['profiles'],
            'flavor': 'PRE_FETCH',
            'drmType': 'widevine',
            'drmVersion': 25,
            'usePsshBox': True,
            'isBranching': False,
            'isNonMember': False,
            'isUIAutoPlay': False,
            'useHttpsStreams': True,
            'imageSubtitleHeight': 1080,
            'uiVersion': G.LOCAL_DB.get_value('ui_version', '', table=TABLE_SESSION),
            'uiPlatform': 'SHAKTI',
            'clientVersion': G.LOCAL_DB.get_value('client_version', '', table=TABLE_SESSION),
            'desiredVmaf': 'plus_lts',  # phone_plus_exp can be used to mobile, not tested
            'supportsPreReleasePin': True,
            'supportsWatermark': True,
            'supportsUnequalizedDownloadables': True,
            'showAllSubDubTracks': False,
            'titleSpecificData': {
                str(kwargs['viewable_id']): {
                    'unletterboxed': True
                }
            },
            'videoOutputInfo': [{
                'type': 'DigitalVideoOutputDescriptor',
                'outputType': 'unknown',
                'supportedHdcpVersions': kwargs['hdcp_version'],
                'isHdcpEngaged': bool(kwargs['hdcp_version'])
            }],
            'preferAssistiveAudio': False
        }
        if kwargs['challenge']:
            params['challenge'] = kwargs['challenge']
        endpoint_url = ENDPOINTS['manifest_v1'] + create_req_params('prefetch/manifest')
        request_data = self.msl_requests.build_request_data('/manifest', params)
        return endpoint_url, request_data

    def _build_manifest_v2(self, **kwargs):
        params = {
            'type': 'standard',
            'manifestVersion': 'v2',
            'viewableId': kwargs['viewable_id'],
            'profiles': kwargs['profiles'],
            'flavor': 'PRE_FETCH',  # PRE_FETCH / STANDARD
            'drmType': 'widevine',
            'drmVersion': 25,
            'usePsshBox': True,
            'isBranching': False,
            'useHttpsStreams': True,
            'supportsUnequalizedDownloadables': True,
            'imageSubtitleHeight': 1080,
            'uiVersion': G.LOCAL_DB.get_value('ui_version', '', table=TABLE_SESSION),
            'uiPlatform': 'SHAKTI',
            'clientVersion': G.LOCAL_DB.get_value('client_version', '', table=TABLE_SESSION),
            'platform': G.LOCAL_DB.get_value('browser_info_version', '', table=TABLE_SESSION),
            'osVersion': G.LOCAL_DB.get_value('browser_info_os_version', '', table=TABLE_SESSION),
            'osName': G.LOCAL_DB.get_value('browser_info_os_name', '', table=TABLE_SESSION),
            'supportsPreReleasePin': True,
            'supportsWatermark': True,
            'showAllSubDubTracks': False,
            'videoOutputInfo': [{
                'type': 'DigitalVideoOutputDescriptor',
                'outputType': 'unknown',
                'supportedHdcpVersions': kwargs['hdcp_version'],
                'isHdcpEngaged': bool(kwargs['hdcp_version'])
            }],
            'titleSpecificData': {
                str(kwargs['viewable_id']): {
                    'unletterboxed': True
                }
            },
            'preferAssistiveAudio': False,
            'isUIAutoPlay': False,
            'isNonMember': False,
            'desiredVmaf': 'plus_lts',  # phone_plus_exp can be used to mobile, not tested
            'desiredSegmentVmaf': 'plus_lts',
            'requestSegmentVmaf': False,
            'supportsPartialHydration': False,
            'contentPlaygraph': ['start'],
            'liveMetadataFormat': 'INDEXED_SEGMENT_TEMPLATE',
            'useBetterTextUrls': True,
            'profileGroups': [{
                'name': 'default',
                'profiles': kwargs['profiles']
            }],
            'challenge': kwargs['challenge'],
            'challenges': {
                'default': [{
                    'drmSessionId': kwargs['sid'] or 'session',
                    'clientTime': int(time.time()),
                    'challengeBase64': kwargs['challenge']
                }]},
            # License type:
            # - 'limited' license data provided in the manifest response, may be needed a second license request
            # - 'standard' no license data provided in the manifest response
            # TODO: Currently on linux only the license type set to "limited" cause this error on ISA:
            #  License update not successful (no keys)
            'licenseType': 'standard'
        }
        # 30/10/2022 on linux xid must be specified on the challenge dict
        # otherwise ISA raise error: License update not successful (no keys)
        if common.get_system_platform() == 'linux':
            params['challenges']['default'][0]['xid'] = kwargs['xid']
        else:
            params['xid'] = kwargs['xid']

        endpoint_url = ENDPOINTS['manifest'] + create_req_params('licensedManifest')
        request_data = self.msl_requests.build_request_data('licensedManifest', params)
        return endpoint_url, request_data

    @display_error_info
    @measure_exec_time_decorator(is_immediate=True)
    def get_license(self, license_data):
        """
        Requests and returns a license for the given challenge and sid

        :param license_data: The license data provided by isa
        :return: Base64 representation of the license key or False unsuccessful
        """
        if self.needs_license_request:
            LOG.debug('Requesting license')
            challenge, sid = license_data.decode('utf-8').split('!')
            sid = base64.standard_b64decode(sid).decode('utf-8')
            xid = G.LOCAL_DB.get_value('xid', '', table=TABLE_SESSION)
            params = [{
                'drmSessionId': sid,
                'clientTime': int(time.time()),
                'challengeBase64': challenge,
                'xid': xid
            }]
            endpoint_url = ENDPOINTS['license'] + create_req_params('prefetch/license')
            try:
                response = self.msl_requests.chunked_request(endpoint_url,
                                                             self.msl_requests.build_request_data(self.last_license_url,
                                                                                                  params,
                                                                                                  'drmSessionId'),
                                                             get_esn())
            except MSLError as exc:
                if exc.err_number == '1044' and common.get_system_platform() == 'android':
                    msg = ('This title is not available to watch instantly. Please try another title.\r\n'
                           'To try to solve this problem you can force "Widevine L3" from the add-on Expert settings.\r\n'
                           'More info in the Wiki FAQ on add-on GitHub.')
                    raise MSLError(msg) from exc
                raise
            # If this is a second license request from ISAdaptive then update the previous license data
            # so when we "release" the license we release the last one
            if len(self.licenses_xid) > 1 and self.licenses_xid[0] == xid:
                self.licenses_session_id[0] = sid
                self.licenses_release_url[0] = response[0]['links']['releaseLicense']['href']
            else:
                self.licenses_xid.insert(0, xid)
                self.licenses_session_id.insert(0, sid)
                self.licenses_release_url.insert(0, response[0]['links']['releaseLicense']['href'])
            response_data = base64.standard_b64decode(response[0]['licenseResponseBase64'])
        else:
            LOG.debug('Get manifest license')
            # With licensed manifest with licenseType limited InputStream Adaptive may request license a second time
            self.needs_license_request = True
            response_data = base64.standard_b64decode(self.licenses_response)
        return response_data

    @display_error_info
    @measure_exec_time_decorator(is_immediate=True)
    def release_license(self):
        """Release the server license"""
        try:
            # When you try to play a video while another one is currently in playing,
            # a new license to be released will be queued, so the oldest license must be released
            url = self.licenses_release_url.pop()
            sid = self.licenses_session_id.pop()
            xid = self.licenses_xid.pop()
            LOG.debug('Requesting releasing license')
            params = [{
                'url': url,
                'params': {
                    'drmSessionId': sid,
                    'xid': str(xid)
                },
                'echo': 'drmSessionId'
            }]
            endpoint_url = ENDPOINTS['license'] + create_req_params('release/license')
            response = self.msl_requests.chunked_request(endpoint_url,
                                                         self.msl_requests.build_request_data('/bundle', params),
                                                         get_esn())
            LOG.debug('License release response: {}', response)
        except IndexError:
            # Example the supplemental media type have no license
            LOG.debug('No license to release')

    def clear_user_id_tokens(self):
        """Clear all user id tokens"""
        self.msl_requests.crypto.clear_user_id_tokens()

    @measure_exec_time_decorator(is_immediate=True)
    def _tranform_to_dash(self, manifest):
        return convert_to_dash(manifest)
