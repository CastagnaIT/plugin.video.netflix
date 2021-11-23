# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT (original implementation module)
    Manages events to send to the netflix service for the progress of the played video

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from typing import TYPE_CHECKING

from resources.lib import common
from resources.lib.common.cache_utils import CACHE_BOOKMARKS, CACHE_COMMON, CACHE_MANIFESTS
from resources.lib.common.exceptions import InvalidVideoListTypeError
from resources.lib.globals import G
from resources.lib.services.nfsession.msl.msl_utils import EVENT_ENGAGE, EVENT_START, EVENT_STOP, EVENT_KEEP_ALIVE
from resources.lib.utils.api_paths import build_paths, EVENT_PATHS
from resources.lib.utils.esn import get_esn
from resources.lib.utils.logging import LOG
from .action_manager import ActionManager

if TYPE_CHECKING:  # This variable/imports are used only by the editor, so not at runtime
    from resources.lib.services.nfsession.nfsession_ops import NFSessionOperations
    from resources.lib.services.nfsession.directorybuilder.dir_builder import DirectoryBuilder
    from resources.lib.services.nfsession.msl.msl_handler import MSLHandler


class AMVideoEvents(ActionManager):
    """Detect the progress of the played video and send the data to the netflix service"""

    SETTING_ID = 'sync_watched_status'

    def __init__(self, nfsession: 'NFSessionOperations', msl_handler: 'MSLHandler',
                 directory_builder: 'DirectoryBuilder'):
        super().__init__()
        self.nfsession = nfsession
        self.msl_handler = msl_handler
        self.directory_builder = directory_builder
        self.event_data = {}
        self.is_event_start_sent = False
        self.last_tick_count = 0
        self.tick_elapsed = 0
        self.is_player_in_pause = False
        self.lock_events = False
        self.allow_request_update_loco = False

    def __str__(self):
        return f'enabled={self.enabled}'

    def initialize(self, data):
        if self.videoid.mediatype not in [common.VideoId.MOVIE, common.VideoId.EPISODE]:
            LOG.warn('AMVideoEvents: disabled due to no not supported videoid mediatype')
            self.enabled = False
            return
        if (not data['is_played_from_strm'] or
                (data['is_played_from_strm'] and G.ADDON.getSettingBool('sync_watched_status_library'))):
            self.event_data = self._get_event_data(self.videoid)
            self.event_data['videoid'] = self.videoid
            self.event_data['is_played_by_library'] = data['is_played_from_strm']
        else:
            self.enabled = False

    def on_playback_started(self, player_state):
        self.event_data['manifest'] = _get_manifest(self.videoid)
        # Clear continue watching list data on the cache, to force loading of new data
        # but only when the videoid not exists in the continue watching list
        try:
            videoid_exists, list_id = self.directory_builder.get_continuewatching_videoid_exists(
                str(self.videoid_parent.value))
            if not videoid_exists:
                # Delete the cache of continueWatching list
                G.CACHE.delete(CACHE_COMMON, list_id, including_suffixes=True)
                # When the continueWatching context is invalidated from a refreshListByContext call
                # the LoCo need to be updated to obtain the new list id, so we delete the cache to get new data
                G.CACHE.delete(CACHE_COMMON, 'loco_list')
        except InvalidVideoListTypeError:
            # Ignore possible "No lists with context xxx available" exception due to a new profile without data
            pass

    def on_tick(self, player_state):
        if self.lock_events:
            return
        if self.is_player_in_pause and (self.tick_elapsed - self.last_tick_count) >= 1800:
            # When the player is paused for more than 30 minutes we interrupt the sending of events (1800secs=30m)
            self._send_event(EVENT_ENGAGE, self.event_data, player_state)
            self._send_event(EVENT_STOP, self.event_data, player_state)
            self.is_event_start_sent = False
            self.lock_events = True
        else:
            if not self.is_event_start_sent:
                # We do not use _on_playback_started() to send EVENT_START, because the action managers
                # AMStreamContinuity and AMPlayback may cause inconsistencies with the content of player_state data

                # When the playback starts for the first time, for correctness should send elapsed_seconds value to 1
                if self.tick_elapsed < 5 and self.event_data['resume_position'] is None:
                    player_state['elapsed_seconds'] = 1
                self._send_event(EVENT_START, self.event_data, player_state)
                self.is_event_start_sent = True
                self.tick_elapsed = 0
            else:
                # Generate events to send to Netflix service every 1 minute (60secs=1m)
                if (self.tick_elapsed - self.last_tick_count) >= 60:
                    self._send_event(EVENT_KEEP_ALIVE, self.event_data, player_state)
                    self._save_resume_time(player_state['elapsed_seconds'])
                    self.last_tick_count = self.tick_elapsed
                    # Allow request of loco update (for continueWatching and bookmark) only after the first minute
                    # it seems that most of the time if sent earlier returns error
                    self.allow_request_update_loco = True
        self.tick_elapsed += 1  # One tick almost always represents one second

    def on_playback_pause(self, player_state):
        if not self.is_event_start_sent:
            return
        self._reset_tick_count()
        self.is_player_in_pause = True
        self._send_event(EVENT_ENGAGE, self.event_data, player_state)
        self._save_resume_time(player_state['elapsed_seconds'])

    def on_playback_resume(self, player_state):
        self.is_player_in_pause = False
        self.lock_events = False

    def on_playback_seek(self, player_state):
        if not self.is_event_start_sent or self.lock_events:
            # This might happen when the action manager AMPlayback perform a video skip
            return
        self._reset_tick_count()
        self._send_event(EVENT_ENGAGE, self.event_data, player_state)
        self._save_resume_time(player_state['elapsed_seconds'])
        self.allow_request_update_loco = True

    def on_playback_stopped(self, player_state):
        if not self.is_event_start_sent or self.lock_events:
            return
        self._reset_tick_count()
        self._send_event(EVENT_ENGAGE, self.event_data, player_state)
        self._send_event(EVENT_STOP, self.event_data, player_state)
        # Update the resume here may not always work due to race conditions with GUI directory refresh and Stop event
        self._save_resume_time(player_state['elapsed_seconds'])

    def _save_resume_time(self, resume_time):
        """Save resume time value in order to update the infolabel cache"""
        # Why this, the video lists are requests to the web service only once and then will be cached in order to
        # quickly get the data and speed up a lot the GUI response.
        # Watched status of a (video) list item is based on resume time, and the resume time is saved in the cache data.
        # To avoid slowing down the GUI by invalidating the cache to get new data from website service, one solution is
        # save the values in memory and override the bookmark value of the infolabel.
        # The callback _on_playback_stopped can not be used, because the loading of frontend happen before.
        G.CACHE.add(CACHE_BOOKMARKS, self.videoid.value, resume_time)

    def _reset_tick_count(self):
        self.tick_elapsed = 0
        self.last_tick_count = 0

    def _send_event(self, event_type, event_data, player_state):
        if not player_state:
            LOG.warn('AMVideoEvents: the event [{}] cannot be sent, missing player_state data', event_type)
            return
        event_data['allow_request_update_loco'] = self.allow_request_update_loco
        self.msl_handler.events_handler_thread.add_event_to_queue(event_type,
                                                                  event_data,
                                                                  player_state)

    def _get_event_data(self, videoid):
        """Get data needed to send event requests to Netflix"""
        is_episode = videoid.mediatype == common.VideoId.EPISODE
        req_videoids = [videoid]
        if is_episode:
            # Get also the tvshow data
            req_videoids.append(videoid.derive_parent(common.VideoId.SHOW))

        raw_data = self._get_video_raw_data(req_videoids)
        if not raw_data:
            return {}
        LOG.debug('Event data: {}', raw_data)
        videoid_data = raw_data['videos'][videoid.value]

        if is_episode:
            # Get inQueue from tvshow data
            is_in_mylist = raw_data['videos'][str(req_videoids[1].value)]['queue'].get('inQueue', False)
        else:
            is_in_mylist = videoid_data['queue'].get('inQueue', False)

        resume_position = videoid_data['bookmarkPosition'] if videoid_data['bookmarkPosition'] > -1 else None
        event_data = {'resume_position': resume_position,
                      'runtime': videoid_data['runtime'],
                      'request_id': videoid_data['requestId'],
                      'watched': videoid_data['watched'],
                      'is_in_mylist': is_in_mylist}
        if videoid.mediatype == common.VideoId.EPISODE:
            event_data['track_id'] = videoid_data['trackIds']['trackId_jawEpisode']
        else:
            event_data['track_id'] = videoid_data['trackIds']['trackId_jaw']
        return event_data

    def _get_video_raw_data(self, videoids):
        """Retrieve raw data for specified video id's"""
        video_ids = [int(videoid.value) for videoid in videoids]
        LOG.debug('Requesting video raw data for {}', video_ids)
        return self.nfsession.path_request(build_paths(['videos', video_ids], EVENT_PATHS))


def _get_manifest(videoid):
    """Get the manifest from cache"""
    cache_identifier = f'{get_esn()}_{videoid.value}'
    return G.CACHE.get(CACHE_MANIFESTS, cache_identifier)
