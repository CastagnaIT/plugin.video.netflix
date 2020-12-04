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

from future.utils import raise_from

import xbmcaddon

import resources.lib.common as common
from resources.lib.common.cache_utils import CACHE_MANIFESTS
from resources.lib.common.exceptions import CacheMiss, MSLError
from resources.lib.database.db_utils import TABLE_SESSION
from resources.lib.globals import G
from resources.lib.utils.esn import get_esn
from resources.lib.utils.logging import LOG, measure_exec_time_decorator
from .converter import convert_to_dash
from .events_handler import EventsHandler
from .msl_requests import MSLRequests
from .msl_utils import ENDPOINTS, display_error_info, MSL_DATA_FILENAME, create_req_params
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
    manifest_challenge = ('CAESwQsKhgsIARLsCQqvAggCEhGN3Th6q2GhvXw9bD+X9aW2ChjQ8PLmBSKOAjCCAQoCggEBANsVUL5yI9K'
                          'UG1TPpb1A0bzk6df3YwbpDEkh+IOj52RfnKyspASRN1JQvCRrKwiq433M9BV+8ZkzkheYEPZ9X5rl5Ydkwp'
                          'qedzdZRAiuaVp/mMA5zUM3I3fZogVxGnVzh4mB2URg+g7TFwbPWz2x1uzPumO+2ImOPIUyR7auoOKrZml30'
                          '8w8Edwdd1HwFyrJEZHLDN2P51PJhVrUBWUlxebY05NhfIUvWQ/pyXAa6AahTf7PTVow/uu1d0vc6gHSxmj0'
                          'hodvaxrkDcBY9NoOH2XCW7LNJnKC487CVwCHOJC9+6fakaHnjHepayeGEp2JL2AaCrGGqAOZdG8F11Pa0H8'
                          'CAwEAASirbxKAAmFqOFvUp7caxO5/q2QK5yQ8/AA5E1KOQJxZrqwREPbGUX3670XGw9bamA0bxc37DUi6Dw'
                          'rOyWKWSaW/qVNie86mW/7KdVSpZPGcF/TxO+kd4iXMIjH0REZst/mMJhv5UMMO9dDFGR3RBqkPbDTdzvX1u'
                          'E/loVPDH8QEfDACzDkeCA1P0zAcjWKGPzaeUrogsnBEQN4wCVRQqufDXkgImhDUCUkmyQDJXQkhgMMWtbbC'
                          'HMa/DMGEZAhu4I8G32m8XxU3NoK1kDsb+s5VUgOdkX3ZnFw1uf3niQ9FCTYlzv4SIBJGEokJjkHagT6kVWf'
                          'hsvSHMHzayKb00OwIn/6NsNEatAUKrgIIARIQiX9ghrmqxsdcq/w8cprG8Bj46/LmBSKOAjCCAQoCggEBAL'
                          'udF8e+FexCGnOsPQCNtaIvTRW8XsqiTxdo5vElAnGMoOZn6Roy2jwDkc1Gy2ucybY926xk0ZP2Xt5Uy/atI'
                          '5yAvn7WZGWzbR5BbMbXIxaCyDysm7L+X6Fid55YbJ8GLl2/ToOY2CVYT+EciaTj56OjcyBJLDW/0Zqp25gn'
                          'da61HwomZOVLoFmLbeZtC5DjvEv8c2NIDXXketqd/vj0I1nWKtEy8nKIPw/2nhitR6QFUnfEb8hJgPgdTAp'
                          'TkxWm4hSpWsM0j8CQOYNzDL2/kfP1cYw0Fh7oJMSEt2H6AUjC4lIkp54rPHAhLYE+tmwKSYfrmjEoTVErcI'
                          'jl6jEvwtsCAwEAASirbxKAA0OHZIfwXbTghTVi4awHyXje/8D5fdtggtTa0Edec0KmZbHwBbLJ9OCBc9RrR'
                          'L8O4WgQPG/5RVLc9IsR9x/Gw1vg/X+MmWEBnY62XNdVAUjbYGwRQuHQFMkwEQdzxfcH9oWoJtOZdLEN2X/p'
                          'Ws7MeM4KZc8gTUqcDHekq1QqKNs+Voc8Q5hIX7fims9llY/RUHNatDPFVuEyJ0Vqx5l+Rrrdqk+b1fXuVR6'
                          'yxP1h4S/C/UtedUyZxZgc/1OJ0mLr5x1tkRbFVyzA8Z/qfZeYq3HV4pAGg7nLg0JRBTbjiZH8eUhr1JtwLi'
                          'udU9vLvDnv1Y6bsfaT62vfLOttozSZVIeWo7acZHICduOL/tH1Kx7f6e7ierwQYAOng1LGs/PLofQ874C1A'
                          'tNkN0tVe6cSSAvN+Vl33GbICXpX6Rq8LBPqqhzGMGBMiybnmXqOaXz8ngSQCiXqp/ImaOKfx8OE6qH92rUV'
                          'Wgw68qBy9ExEOl95SSEx9A/B4vEYFHaHwzqh2BoYChFhcmNoaXRlY3R1cmVfbmFtZRIDYXJtGhYKDGNvbXB'
                          'hbnlfbmFtZRIGR29vZ2xlGhcKCm1vZGVsX25hbWUSCUNocm9tZUNETRoZCg1wbGF0Zm9ybV9uYW1lEghDaH'
                          'JvbWVPUxojChR3aWRldmluZV9jZG1fdmVyc2lvbhILNC4xMC4xNjEwLjYyCAgBEAAYACABEiwKKgoUCAESE'
                          'AAAAAAD0mdJAAAAAAAAAAAQARoQA5cwqbEo4TSV6p1qQZy26BgBIOSrw/cFMBUagAIp7zGUC9p3XZ9sp0w+'
                          'yd6/wyRa1V22NyPF4BsNivSEkMtcEaQiUOW+LrGhHO+RrukWeJlzVbtpai5/vjOAbsaouQ0yMp8yfpquZcV'
                          'kpPugSOPKu1A0W5w5Ou9NOGsMaJi6+LicGxhS+7xAp/lv/9LATCcQJXS2elBCz6f6VUQyMOPyjQYBrH3h27'
                          'tVRcsnTRQATcogwCytXohKroBGvODIYcpVFsy2saOCyh4HTezzXJvgogx2f15ViyF5rDqho4YsW0z4it9TF'
                          'BT0OOLkk0fQ6a1LSqA49eN3RufKYq4LT+G+ffdgoDmKpIWS3bp7xQ6GeYtDAUh0D8Ipwc8aKzP2')

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
            msl_data = json.loads(common.load_file_def(MSL_DATA_FILENAME))
            LOG.info('Loaded MSL data from disk')
        except Exception:  # pylint: disable=broad-except
            msl_data = None
        self.msl_requests = MSLRequests(msl_data)
        self.switch_events_handler()

    def reinitialize_msl_handler(self, data=None):  # pylint: disable=unused-argument
        """
        Reinitialize the MSL handler
        :param data: set True for delete the msl file data, and then reset all
        """
        LOG.debug('Reinitializing MSL handler')
        if data is True:
            common.delete_file(MSL_DATA_FILENAME)
        self._init_msl_handler()

    def switch_events_handler(self, data=None):
        """Switch to enable or disable the Events handler"""
        if self._events_handler_thread:
            self._events_handler_thread.stop_join()
            self._events_handler_thread = None
        if G.ADDON.getSettingBool('ProgressManager_enabled') or data:
            self._events_handler_thread = EventsHandler(self.msl_requests.chunked_request)
            self._events_handler_thread.start()

    @display_error_info
    @measure_exec_time_decorator(is_immediate=True)
    def load_manifest(self, viewable_id):
        """
        Loads the manifests for the given viewable_id and returns a mpd-XML-Manifest

        :param viewable_id: The id of of the viewable
        :return: MPD XML Manifest or False if no success
        """
        try:
            manifest = self._load_manifest(viewable_id, get_esn())
        except MSLError as exc:
            if 'Email or password is incorrect' in G.py2_decode(str(exc)):
                # Known cases when MSL error "Email or password is incorrect." can happen:
                # - If user change the password when the nf session was still active
                # - Netflix has reset the password for suspicious activity when the nf session was still active
                # Then clear the credentials and also user tokens.
                common.purge_credentials()
                self.msl_requests.crypto.clear_user_id_tokens()
            raise
        return self.__tranform_to_dash(manifest)

    @measure_exec_time_decorator(is_immediate=True)
    def _load_manifest(self, viewable_id, esn):
        cache_identifier = esn + '_' + unicode(viewable_id)
        try:
            # The manifest must be requested once and maintained for its entire duration
            manifest = G.CACHE.get(CACHE_MANIFESTS, cache_identifier)
            expiration = int(manifest['expiration'] / 1000)
            if (expiration - time.time()) < 14400:
                # Some devices remain active even longer than 48 hours, if the manifest is at the limit of the deadline
                # when requested by am_stream_continuity.py / events_handler.py will cause problems
                # if it is already expired, so we guarantee a minimum of safety ttl of 4h (14400s = 4 hours)
                raise CacheMiss()
            if LOG.level == LOG.LEVEL_VERBOSE:
                LOG.debug('Manifest for {} obtained from the cache', viewable_id)
                # Save the manifest to disk as reference
                common.save_file_def('manifest.json', json.dumps(manifest).encode('utf-8'))
            return manifest
        except CacheMiss:
            pass

        isa_addon = xbmcaddon.Addon('inputstream.adaptive')
        hdcp_override = isa_addon.getSettingBool('HDCPOVERRIDE')
        hdcp_4k_capable = common.is_device_4k_capable() or G.ADDON.getSettingBool('enable_force_hdcp')

        hdcp_version = []
        if not hdcp_4k_capable and hdcp_override:
            hdcp_version = ['1.4']
        if hdcp_4k_capable and hdcp_override:
            hdcp_version = ['2.2']

        LOG.info('Requesting manifest for {} with ESN {} and HDCP {}',
                 viewable_id,
                 common.censure(esn) if G.ADDON.getSetting('esn') else esn,
                 hdcp_version)

        profiles = enabled_profiles()
        from pprint import pformat
        LOG.info('Requested profiles:\n{}', pformat(profiles, indent=2))

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
            'uiVersion': G.LOCAL_DB.get_value('ui_version', '', table=TABLE_SESSION),
            'uiPlatform': 'SHAKTI',
            'clientVersion': G.LOCAL_DB.get_value('client_version', '', table=TABLE_SESSION),
            'desiredVmaf': 'plus_lts',  # phone_plus_exp can be used to mobile, not tested
            'supportsPreReleasePin': True,
            'supportsWatermark': True,
            'supportsUnequalizedDownloadables': True,
            'showAllSubDubTracks': False,
            'titleSpecificData': {
                unicode(viewable_id): {
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

        if 'linux' in common.get_system_platform() and 'arm' in common.get_machine():
            # 24/06/2020 To get until to 1080P resolutions under arm devices (ChromeOS), android excluded,
            #   is mandatory to add the widevine challenge data (key request) to the manifest request.
            # Is not possible get the key request from the default_crypto, is needed to implement
            #   the wv crypto (used for android) but currently InputStreamAdaptive support this interface only
            #   under android OS.
            # As workaround: Initially we pass an hardcoded challenge data needed to play the first video,
            #   then when ISA perform the license callback we replace it with the fresh license challenge data.
            params['challenge'] = self.manifest_challenge

        endpoint_url = ENDPOINTS['manifest'] + create_req_params(0, 'prefetch/manifest')
        manifest = self.msl_requests.chunked_request(endpoint_url,
                                                     self.msl_requests.build_request_data('/manifest', params),
                                                     esn,
                                                     disable_msl_switch=False)
        if LOG.level == LOG.LEVEL_VERBOSE:
            # Save the manifest to disk as reference
            common.save_file_def('manifest.json', json.dumps(manifest).encode('utf-8'))
        # Save the manifest to the cache to retrieve it during its validity
        expiration = int(manifest['expiration'] / 1000)
        G.CACHE.add(CACHE_MANIFESTS, cache_identifier, manifest, expires=expiration)
        return manifest

    @display_error_info
    @measure_exec_time_decorator(is_immediate=True)
    def get_license(self, challenge, sid):
        """
        Requests and returns a license for the given challenge and sid

        :param challenge: The base64 encoded challenge
        :param sid: The sid paired to the challenge
        :return: Base64 representation of the license key or False unsuccessful
        """
        LOG.debug('Requesting license')

        timestamp = int(time.time() * 10000)
        xid = str(timestamp + 1610)
        params = [{
            'drmSessionId': sid,
            'clientTime': int(timestamp / 10000),
            'challengeBase64': challenge,
            'xid': xid
        }]
        self.manifest_challenge = challenge
        endpoint_url = ENDPOINTS['license'] + create_req_params(0, 'prefetch/license')
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
                raise_from(MSLError(msg), exc)
            raise
        # This xid must be used also for each future Event request, until playback stops
        G.LOCAL_DB.set_value('xid', xid, TABLE_SESSION)

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
        LOG.debug('Requesting bind events')
        endpoint_url = ENDPOINTS['manifest'] + create_req_params(20, 'bind')
        response = self.msl_requests.chunked_request(endpoint_url,
                                                     self.msl_requests.build_request_data('/bind', {}),
                                                     get_esn(),
                                                     disable_msl_switch=False)
        LOG.debug('Bind events response: {}', response)

    @display_error_info
    @measure_exec_time_decorator(is_immediate=True)
    def release_license(self, data=None):  # pylint: disable=unused-argument
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
                    'xid': xid
                },
                'echo': 'drmSessionId'
            }]

            endpoint_url = ENDPOINTS['license'] + create_req_params(10, 'release/license')
            response = self.msl_requests.chunked_request(endpoint_url,
                                                         self.msl_requests.build_request_data('/bundle', params),
                                                         get_esn())
            LOG.debug('License release response: {}', response)
        except IndexError:
            # Example the supplemental media type have no license
            LOG.debug('No license to release')

    def clear_user_id_tokens(self, data=None):  # pylint: disable=unused-argument
        """Clear all user id tokens"""
        self.msl_requests.crypto.clear_user_id_tokens()

    @measure_exec_time_decorator(is_immediate=True)
    def __tranform_to_dash(self, manifest):
        self.last_license_url = manifest['links']['license']['href']
        return convert_to_dash(manifest)
