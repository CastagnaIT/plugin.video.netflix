# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2019 Smeulf (original implementation module)
    Operations for changing the playback status

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import time

import xbmc
import xbmcvfs

import resources.lib.common as common
from resources.lib.globals import G
from resources.lib.utils.logging import LOG
from .action_manager import ActionManager


class AMPlayback(ActionManager):
    """Operations for changing the playback status"""

    SETTING_ID = 'ResumeManager_enabled'

    def __init__(self):
        super().__init__()
        self.resume_position = None
        self.enabled = True
        self.start_time = None
        self.is_player_in_pause = False
        self.is_played_from_strm = False
        self.watched_threshold = None

    def __str__(self):
        return f'enabled={self.enabled}'

    def initialize(self, data):
        self.resume_position = data.get('resume_position')
        self.is_played_from_strm = data['is_played_from_strm']
        if 'watchedToEndOffset' in data['metadata'][0]:
            self.watched_threshold = data['metadata'][0]['watchedToEndOffset']
        elif 'creditsOffset' in data['metadata'][0]:
            # To better ensure that a video is marked as watched also when a user do not reach the ending credits
            # we generally lower the watched threshold by 50 seconds for 50 minutes of video (3000 secs)
            lower_value = data['metadata'][0]['runtime'] / 3000 * 50
            self.watched_threshold = data['metadata'][0]['creditsOffset'] - lower_value

    def on_playback_started(self, player_state):
        self._set_audio_offset(player_state)
        self._set_strm_resume_workaround()

    def _set_audio_offset(self, player_state):
        if not G.ADDON.getSettingBool('audio_offset_enabled'):
            return
        current_offset = common.json_rpc('Player.GetAudioDelay')['offset']
        target_offset = G.ADDON.getSettingNumber('audio_offset')
        if current_offset != target_offset:
            ret = common.json_rpc('Player.SetAudioDelay', {'playerid': player_state['playerid'],
                                                           'offset': target_offset})
            LOG.debug('Audio offset has been set to {}s (player value {}s)', target_offset, ret['offset'])

    def _set_strm_resume_workaround(self):
        # Due to a bug on Kodi (until to v19) the resume on STRM files not works correctly,
        # so we force the skip to the resume point
        if not self.resume_position:
            return
        LOG.info('AMPlayback has forced resume point to {}', self.resume_position)
        xbmc.Player().seekTime(int(self.resume_position))

    def on_tick(self, player_state):
        # Stops playback when paused for more than one hour.
        # Some users leave the playback paused also for more than 12 hours,
        # this complicates things to resume playback, because the manifest data expires and with it also all
        # the streams urls are no longer guaranteed, so we force the stop of the playback.
        if self.is_player_in_pause and (time.time() - self.start_time) > 3600:
            LOG.info('The playback has been stopped because it has been exceeded 1 hour of pause')
            common.stop_playback()

    def on_playback_pause(self, player_state):
        self.start_time = time.time()
        self.is_player_in_pause = True

    def on_playback_resume(self, player_state):
        self.is_player_in_pause = False

    def on_playback_stopped(self, player_state):
        if player_state['nf_is_ads_stream']:
            return
        # It could happen that Kodi does not assign as watched a video,
        # this because the credits can take too much time, then the point where playback is stopped
        # falls in the part that kodi recognizes as unwatched (playcountminimumpercent 90% + no-mans land 2%)
        # https://kodi.wiki/view/HOW-TO:Modify_automatic_watch_and_resume_points#Settings_explained
        # In these cases we try change/fix manually the watched status of the video by using netflix offset data
        if int(player_state['percentage']) > 92:
            return
        if not self.watched_threshold or not player_state['current_pts'] > self.watched_threshold:
            return
        if G.ADDON.getSettingBool('sync_watched_status') and not self.is_played_from_strm:
            # This have not to be applied with our custom watched status of Netflix sync, within the addon
            return
        if self.is_played_from_strm:
            # The current video played is a STRM, then generate the path of a STRM file
            file_path = G.SHARED_DB.get_episode_filepath(
                self.videoid.tvshowid,
                self.videoid.seasonid,
                self.videoid.episodeid)
            url = xbmcvfs.translatePath(file_path)
            common.json_rpc('Files.SetFileDetails',
                            {"file": url, "media": "video", "resume": None, "playcount": 1})
        else:
            url = common.build_url(videoid=self.videoid,
                                   mode=G.MODE_PLAY,
                                   params={'profile_guid': G.LOCAL_DB.get_active_profile_guid()})
            common.json_rpc('Files.SetFileDetails',
                            {"file": url, "media": "video", "resume": None, "playcount": 1})
        LOG.info('Has been fixed the watched status of the video: {}', url)
