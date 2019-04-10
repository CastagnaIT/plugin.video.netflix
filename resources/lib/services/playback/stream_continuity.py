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
        self.current_show = None
        self.current_streams = {}
        self.player = xbmc.Player()
        self.did_restore = False

    @property
    def show_settings(self):
        """Stored stream settings for the current show"""
        return self.storage.get(self.current_show, {})

    def _initialize(self, data):
        if 'tvshowid' in data['videoid']:
            self.did_restore = False
            self.current_show = data['videoid']['tvshowid']
        else:
            self.enabled = False

    def _on_playback_started(self, player_state):
        xbmc.sleep(1000)
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
                self._save_changed_stream(stype, player_stream)

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

    def _save_changed_stream(self, stype, stream):
        common.debug('Save changed stream {} for {}'.format(stream, stype))
        new_show_settings = self.show_settings.copy()
        new_show_settings[stype] = stream
        self.storage[self.current_show] = new_show_settings

    def __repr__(self):
        return ('enabled={}, current_show={}'
                .format(self.enabled, self.current_show))
