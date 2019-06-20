# -*- coding: utf-8 -*-

"""
Remember and restore audio stream / subtitle settings between individual
episodes of a tv show
"""
from __future__ import unicode_literals

import xbmc

from resources.lib.globals import g
import resources.lib.common as common
import resources.lib.kodi.ui as ui

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
        self.storage = common.PersistentStorage(__name__)
        self.current_videoid = None
        self.current_streams = {}
        self.player = xbmc.Player()
        self.did_restore = False
        self.resume = {}

    @property
    def show_settings(self):
        """Stored stream settings for the current show"""
        return self.storage.get(self.current_videoid, {})

    def _initialize(self, data):
        self.resume = data.get('resume', {})
        if 'tvshowid' in data['videoid']:
            self.did_restore = False
            self.current_videoid = data['videoid']['tvshowid']
        elif 'movieid' in data['videoid']:
            self.did_restore = False
            self.current_videoid = data['videoid']['movieid']
        else:
            self.enabled = False

    def _on_playback_started(self, player_state):
        xbmc.sleep(500)
        for stype in STREAMS:
            self._set_current_stream(stype, player_state)
            self._restore_stream(stype)
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
                self._save_all_streams(player_state, stype, player_stream)

    def _set_current_stream(self, stype, player_state):
        self.current_streams.update({
            stype: player_state.get(STREAMS[stype]['current'])
        })

    def _restore_stream(self, stype):
        common.debug('Trying to restore {}...'.format(stype))
        set_stream = STREAMS[stype]['setter']
        stored_stream = self.show_settings.get(stype)
        if (stored_stream is not None and
                self.current_streams[stype] != stored_stream):
            # subtitleenabled is boolean and not a dict
            set_stream(self.player, (stored_stream['index']
                                     if isinstance(stored_stream, dict)
                                     else stored_stream))
            self.current_streams[stype] = stored_stream
            common.debug('Restored {} to {}'.format(stype, stored_stream))

    def _save_all_streams(self, player_state, stype, stream):
        common.debug('Save all streams because a change of {} for {}'.format(stream, stype))
        new_show_settings={}
        for stype in STREAMS:
            player_stream = player_state.get(STREAMS[stype]['current'])
            new_show_settings[stype] = player_stream
        self.storage[self.current_videoid] = new_show_settings
        self.storage.commit()

    def __repr__(self):
        return ('enabled={}, current_videoid={}'
                .format(self.enabled, self.current_videoid))
