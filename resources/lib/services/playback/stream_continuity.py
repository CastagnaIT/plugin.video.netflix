# -*- coding: utf-8 -*-

"""
Remember and restore audio stream / subtitle settings between individual
episodes of a tv show or movie
"""
from __future__ import unicode_literals

import xbmc

import json

from resources.lib.globals import g
import resources.lib.common as common

from .action_manager import PlaybackActionManager

STREAMS = {
    'audio': {
        'current': 'currentaudiostream',
        'setter': xbmc.Player.setAudioStream,
    },
    'subtitle': {
        'current': 'currentsubtitle',
        'setter': xbmc.Player.setSubtitleStream,
    },
    'subtitleenabled': {
        'current': 'subtitleenabled',
        'setter': xbmc.Player.showSubtitles
    }
}


class StreamContinuityManager(PlaybackActionManager):
    """
    Detects changes in audio / subtitle streams during playback, saves them
    for the currently playing show and restores them on subsequent episodes.
    """

    def __init__(self):
        super(StreamContinuityManager, self).__init__()
        self.storage = common.PersistentStorage(__name__, no_save_on_destroy=True)
        self.current_videoid = None
        self.current_streams = {}
        self.player = xbmc.Player()
        self.did_restore = False
        self.resume = {}

    @property
    def sc_settings(self):
        """Stored stream settings for the current videoid"""

        return g.SHARED_DB.get_stream_continuity(g.LOCAL_DB.get_active_profile_guid(),
                                                 self.current_videoid.value, {})

    def _initialize(self, data):
        videoid = common.VideoId.from_dict(data['videoid'])
        if videoid.mediatype in [common.VideoId.MOVIE, common.VideoId.EPISODE]:
            self.did_restore = False
            self.current_videoid = videoid
        else:
            self.enabled = False

    def _on_playback_started(self, player_state):
        xbmc.sleep(500)  # Wait for slower systems
        for stype in STREAMS:
            self._set_current_stream(stype, player_state)
            self._restore_stream(stype)
        if (self.sc_settings.get('subtitleenabled', None) is None
                and g.ADDON.getSettingBool('forced_subtitle_workaround')):
            # Use the workaround only when the user did not change the show subtitle setting
            _show_only_forced_subtitle()
        self.did_restore = True

    def _on_tick(self, player_state):
        if not self.did_restore:
            common.debug('Did not restore streams yet, ignoring tick')
            return
        for stype in STREAMS:
            current_stream = self.current_streams[stype]
            player_stream = player_state.get(STREAMS[stype]['current'])
            if player_stream != current_stream:
                common.debug('{} has changed from {} to {}'
                             .format(stype, current_stream, player_stream))
                self._set_current_stream(stype, player_state)
                self._save_changed_stream(stype, player_stream)

    def _set_current_stream(self, stype, player_state):
        self.current_streams.update({
            stype: player_state.get(STREAMS[stype]['current'])
        })

    def _restore_stream(self, stype):
        common.debug('Trying to restore {}...'.format(stype))
        set_stream = STREAMS[stype]['setter']
        stored_stream = self.sc_settings.get(stype)
        if (stored_stream is not None and
                self.current_streams[stype] != stored_stream):
            # subtitleenabled is boolean and not a dict
            set_stream(self.player, (stored_stream['index']
                                     if isinstance(stored_stream, dict)
                                     else stored_stream))
            self.current_streams[stype] = stored_stream
            common.debug('Restored {} to {}'.format(stype, stored_stream))

    def _save_changed_stream(self, stype, stream):
        common.debug('Save changed stream {} for {}'.format(stream, stype))
        new_sc_settings = self.sc_settings.copy()
        new_sc_settings[stype] = stream
        g.SHARED_DB.set_stream_continuity(g.LOCAL_DB.get_active_profile_guid(),
                                          self.current_videoid.value,
                                          new_sc_settings)

    def __repr__(self):
        return ('enabled={}, current_videoid={}'
                .format(self.enabled, self.current_videoid))


def _show_only_forced_subtitle():
    # When we have "forced only" subtitle setting in Kodi Player, Kodi use this behavior:
    # 1) try to select forced subtitle that matches audio language
    # 2) when missing, try to select the first "regular" subtitle that matches audio language
    # This Kodi behavior is totally non sense.
    # If forced is selected you must not view the regular subtitles
    # There is no other solution than to disable the subtitles manually.
    manifest_data = json.loads(common.load_file('manifest.json'))
    common.fix_locale_languages(manifest_data['timedtexttracks'])
    audio_language = common.get_kodi_audio_language()
    if not any(text_track.get('isForcedNarrative', False) is True and
               text_track['language'] == audio_language
               for text_track in manifest_data['timedtexttracks']):
        xbmc.Player().showSubtitles(False)
