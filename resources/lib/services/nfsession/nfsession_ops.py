# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2020 Stefano Gottardo (original implementation module)
    Provides methods to perform operations within the Netflix session

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import time
from datetime import datetime, timedelta
from future.utils import raise_from

import xbmc

import resources.lib.common as common
import resources.lib.utils.website as website
from resources.lib.common import cache_utils
from resources.lib.common.exceptions import (NotLoggedInError, MissingCredentialsError, WebsiteParsingError,
                                             MbrStatusAnonymousError, MetadataNotAvailable, LoginValidateError,
                                             HttpError401, InvalidProfilesError)
from resources.lib.globals import G
from resources.lib.kodi import ui
from resources.lib.services.nfsession.session.path_requests import SessionPathRequests
from resources.lib.utils import cookies
from resources.lib.utils.logging import LOG, measure_exec_time_decorator


class NFSessionOperations(SessionPathRequests):
    """Provides methods to perform operations within the Netflix session"""

    def __init__(self):
        super(NFSessionOperations, self).__init__()
        # Slot allocation for IPC
        self.slots = [
            self.get_safe,
            self.post_safe,
            self.login,
            self.login_auth_data,
            self.logout,
            self.path_request,
            self.perpetual_path_request,
            self.callpath_request,
            self.fetch_initial_page,
            self.activate_profile,
            self.parental_control_data,
            self.get_metadata,
            self.update_loco_context,
            self.update_videoid_bookmark
        ]
        # Share the activate profile function to SessionBase class
        self.external_func_activate_profile = self.activate_profile
        self.dt_initial_page_prefetch = None
        # Try prefetch login
        if self.prefetch_login():
            try:
                # Try prefetch initial page
                response = self.get_safe('browse')
                api_data = website.extract_session_data(response, update_profiles=True)
                self.auth_url = api_data['auth_url']
                self.dt_initial_page_prefetch = datetime.now()
            except Exception as exc:  # pylint: disable=broad-except
                LOG.warn('Prefetch initial page failed: {}', exc)

    @measure_exec_time_decorator(is_immediate=True)
    def fetch_initial_page(self):
        """Fetch initial page"""
        # It is mandatory fetch initial page data at every add-on startup to prevent/check possible side effects:
        # - Check if the account subscription is regular
        # - Avoid TooManyRedirects error, can happen when the profile used in nf session actually no longer exists
        # - Refresh the session data
        # - Update the profiles (and sanitize related features) without submitting another request
        if self.dt_initial_page_prefetch and datetime.now() <= self.dt_initial_page_prefetch + timedelta(minutes=30):
            # We do not know if/when the user will open the add-on, some users leave the device turned on more than 24h
            # then we limit the prefetch validity to 30 minutes
            self.dt_initial_page_prefetch = None
            return
        LOG.debug('Fetch initial page')
        from requests import exceptions
        try:
            response = self.get_safe('browse')
            api_data = self.website_extract_session_data(response, update_profiles=True)
            self.auth_url = api_data['auth_url']
        except exceptions.TooManyRedirects:
            # This error can happen when the profile used in nf session actually no longer exists,
            # something wrong happen in the session then the server try redirect to the login page without success.
            # (CastagnaIT: i don't know the best way to handle this borderline case, but login again works)
            self.session.cookies.clear()
            self.login()

    @measure_exec_time_decorator(is_immediate=True)
    def activate_profile(self, guid):
        """Set the profile identified by guid as active"""
        LOG.debug('Switching to profile {}', guid)
        if xbmc.Player().isPlayingVideo():
            # Change the current profile while a video is playing can cause problems with outgoing HTTP requests
            # (MSL/NFSession) causing a failure in the HTTP request or sending data on the wrong profile
            raise Warning('It is not possible select a profile while a video is playing.')
        current_active_guid = G.LOCAL_DB.get_active_profile_guid()
        if guid == current_active_guid:
            LOG.info('The profile guid {} is already set, activation not needed.', guid)
            return
        timestamp = time.time()
        LOG.info('Activating profile {}', guid)
        # 20/05/2020 - The method 1 not more working for switching PIN locked profiles
        # INIT Method 1 - HTTP mode
        # response = self._get('switch_profile', params={'tkn': guid})
        # self.nfsession.auth_url = self.website_extract_session_data(response)['auth_url']
        # END Method 1
        # INIT Method 2 - API mode
        try:
            self.get_safe(endpoint='activate_profile',
                          params={'switchProfileGuid': guid,
                                  '_': int(timestamp * 1000),
                                  'authURL': self.auth_url})
        except HttpError401 as exc:
            # Profile guid not more valid
            raise_from(InvalidProfilesError('Unable to access to the selected profile.'),
                       exc)
        # Retrieve browse page to update authURL
        response = self.get_safe('browse')
        self.auth_url = website.extract_session_data(response)['auth_url']
        # END Method 2

        G.LOCAL_DB.switch_active_profile(guid)
        G.CACHE_MANAGEMENT.identifier_prefix = guid
        cookies.save(self.session.cookies)

    def parental_control_data(self, guid, password):
        # Ask to the service if password is right and get the PIN status
        from requests import exceptions
        try:
            response = self.post_safe('profile_hub',
                                      data={'destination': 'contentRestrictions',
                                            'guid': guid,
                                            'password': password,
                                            'task': 'auth'})
            if response.get('status') != 'ok':
                LOG.warn('Parental control status issue: {}', response)
                raise MissingCredentialsError
        except exceptions.HTTPError as exc:
            if exc.response.status_code == 500:
                # This endpoint raise HTTP error 500 when the password is wrong
                raise_from(MissingCredentialsError, exc)
            raise
        # Warning - parental control levels vary by country or region, no fixed values can be used
        # Note: The language of descriptions change in base of the language of selected profile
        response_content = self.get_safe('restrictions',
                                         data={'password': password},
                                         append_to_address=guid)
        extracted_content = website.extract_parental_control_data(response_content, response['maturity'])
        response['profileInfo']['profileName'] = website.parse_html(response['profileInfo']['profileName'])
        extracted_content['data'] = response
        return extracted_content

    def website_extract_session_data(self, content, **kwargs):
        """Extract session data and handle errors"""
        try:
            return website.extract_session_data(content, **kwargs)
        except WebsiteParsingError as exc:
            LOG.error('An error occurs in extract session data: {}', exc)
            raise
        except (LoginValidateError, MbrStatusAnonymousError) as exc:
            LOG.warn('The session data is not more valid ({})', type(exc).__name__)
            common.purge_credentials()
            self.session.cookies.clear()
            common.send_signal(signal=common.Signals.CLEAR_USER_ID_TOKENS)
            raise_from(NotLoggedInError, exc)

    @measure_exec_time_decorator(is_immediate=True)
    def get_metadata(self, videoid, refresh=False):
        """Retrieve additional metadata for the given VideoId"""
        if isinstance(videoid, list):  # IPC call send the videoid as "path" list
            videoid = common.VideoId.from_path(videoid)
        # Get the parent VideoId (when the 'videoid' is a type of EPISODE/SEASON)
        parent_videoid = videoid.derive_parent(common.VideoId.SHOW)
        # Delete the cache if we need to refresh the all metadata
        if refresh:
            G.CACHE.delete(cache_utils.CACHE_METADATA, str(parent_videoid))
        if videoid.mediatype == common.VideoId.EPISODE:
            try:
                metadata_data = self._episode_metadata(videoid, parent_videoid)
            except KeyError as exc:
                # The episode metadata not exist (case of new episode and cached data outdated)
                # In this case, delete the cache entry and try again safely
                LOG.debug('find_episode_metadata raised an error: {}, refreshing cache', exc)
                try:
                    metadata_data = self._episode_metadata(videoid, parent_videoid, refresh_cache=True)
                except KeyError as exc:
                    # The new metadata does not contain the episode
                    LOG.error('Episode metadata not found, find_episode_metadata raised an error: {}', exc)
                    raise_from(MetadataNotAvailable, exc)
        else:
            metadata_data = self._metadata(video_id=parent_videoid), None
        return metadata_data

    def _episode_metadata(self, episode_videoid, tvshow_videoid, refresh_cache=False):
        if refresh_cache:
            G.CACHE.delete(cache_utils.CACHE_METADATA, str(tvshow_videoid))
        show_metadata = self._metadata(video_id=tvshow_videoid)
        episode_metadata, season_metadata = common.find_episode_metadata(episode_videoid, show_metadata)
        return episode_metadata, season_metadata, show_metadata

    @cache_utils.cache_output(cache_utils.CACHE_METADATA, identify_from_kwarg_name='video_id', ignore_self_class=True)
    def _metadata(self, video_id):
        """Retrieve additional metadata for a video.
        This is a separate method from get_metadata() to work around caching issues
        when new episodes are added to a tv show by Netflix."""
        LOG.debug('Requesting metadata for {}', video_id)
        metadata_data = self.get_safe(endpoint='metadata',
                                      params={'movieid': video_id.value,
                                              '_': int(time.time() * 1000)})
        if not metadata_data:
            # This return empty
            # - if the metadata is no longer available
            # - if it has been exported a tv show/movie from a specific language profile that is not
            #   available using profiles with other languages
            raise MetadataNotAvailable
        return metadata_data['video']

    def update_loco_context(self, context_name):
        """Update a loco list by context"""
        # Call this api seem no more needed to update the continueWatching loco list
        # Get current loco root data
        loco_data = self.path_request([['loco', [context_name], ['context', 'id', 'index']]])
        loco_root = loco_data['loco'][1]
        if 'continueWatching' in loco_data['locos'][loco_root]:
            context_index = loco_data['locos'][loco_root]['continueWatching'][2]
            context_id = loco_data['locos'][loco_root][context_index][1]
        else:
            # In the new profiles, there is no 'continueWatching' list and no list is returned
            LOG.warn('update_loco_context: Update skipped due to missing context {}', context_name)
            return

        path = [['locos', loco_root, 'refreshListByContext']]
        # After the introduction of LoCo, the following notes are to be reviewed (refers to old LoLoMo):
        #   The fourth parameter is like a request-id, but it does not seem to match to
        #   serverDefs/date/requestId of reactContext nor to request_id of the video event request,
        #   seem to have some kind of relationship with renoMessageId suspect with the logblob but i am not sure.
        #   I noticed also that this request can also be made with the fourth parameter empty.
        params = [common.enclose_quotes(context_id),
                  context_index,
                  common.enclose_quotes(context_name),
                  '']
        # path_suffixs = [
        #    [{'from': 0, 'to': 100}, 'itemSummary'],
        #    [['componentSummary']]
        # ]
        try:
            response = self.callpath_request(path, params)
            LOG.debug('refreshListByContext response: {}', response)
            # The call response return the new context id of the previous invalidated loco context_id
            # and if path_suffixs is added return also the new video list data
        except Exception as exc:  # pylint: disable=broad-except
            LOG.warn('refreshListByContext failed: {}', exc)
            if not LOG.level == LOG.LEVEL_VERBOSE:
                return
            ui.show_notification(title=common.get_local_string(30105),
                                 msg='An error prevented the update the loco context on Netflix',
                                 time=10000)

    def update_videoid_bookmark(self, video_id):
        """Update the videoid bookmark position"""
        # You can check if this function works through the official android app
        # by checking if the red status bar of watched time position appears and will be updated, or also
        # if continueWatching list will be updated (e.g. try to play a new tvshow not contained in the "my list")
        call_paths = [['refreshVideoCurrentPositions']]
        params = ['[' + video_id + ']', '[]']
        try:
            response = self.callpath_request(call_paths, params)
            LOG.debug('refreshVideoCurrentPositions response: {}', response)
        except Exception as exc:  # pylint: disable=broad-except
            LOG.warn('refreshVideoCurrentPositions failed: {}', exc)
            ui.show_notification(title=common.get_local_string(30105),
                                 msg='An error prevented the update the status watched on Netflix',
                                 time=10000)
