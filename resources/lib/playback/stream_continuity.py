# -*- coding: utf-8 -*-
# Author: caphm
# Module: stream_continuity
# Created on: 02.08.2018
# License: MIT https://goo.gl/5bMj3H
# pylint: disable=import-error

"""
Remember and restore audio stream / subtitle settings between individual
episodes of a tv show
"""
import xbmc

from resources.lib.ui import xmldialogs, show_modal_dialog
from resources.lib.playback import PlaybackActionManager

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
    def __init__(self, nx_common):
        super(StreamContinuityManager, self).__init__(nx_common)
        self.storage = nx_common.get_storage(__name__)
        self.current_show = None
        self.current_streams = {}
        self.player = xbmc.Player()
        self.did_restore = False

    @property
    def show_settings(self):
        """Stored stream settings for the current show"""
        return self.storage.get(self.current_show, {})

    def _initialize(self, data):
        self.did_restore = False
        # let this throw a KeyError to disable this instance if the playback is
        # not a TV show
        self.current_show = data['tvshow_video_id']

    def _on_playback_started(self, player_state):
        xbmc.sleep(1000)
        for stype in STREAMS:
            self._set_current_stream(stype, player_state)
            self._restore_stream(stype)
        self.did_restore = True

    def _on_tick(self, player_state):
        if not self.did_restore:
            self.log('Did not restore streams yet, ignoring tick')
            return

        for stype in STREAMS:
            current_stream = self.current_streams[stype]
            player_stream = player_state.get(STREAMS[stype]['current'])
            if player_stream != current_stream:
                self.log('{} has changed from {} to {}'
                         .format(stype, current_stream, player_stream))
                self._set_current_stream(stype, player_state)
                self._ask_to_save(stype, player_stream)

    def _set_current_stream(self, stype, player_state):
        self.current_streams.update({
            stype: player_state.get(STREAMS[stype]['current'])
        })

    def _restore_stream(self, stype):
        self.log('Trying to restore {}...'.format(stype))
        set_stream = STREAMS[stype]['setter']
        stored_stream = self.show_settings.get(stype)
        if (stored_stream is not None and
                self.current_streams[stype] != stored_stream):
            # subtitleenabled is boolean and not a dict
            set_stream(self.player, (stored_stream['index']
                                     if isinstance(stored_stream, dict)
                                     else stored_stream))
            self.current_streams[stype] = stored_stream
            self.log('Restored {} to {}'.format(stype, stored_stream))

    def _ask_to_save(self, stype, stream):
        self.log('Asking to save {} for {}'.format(stream, stype))
        new_show_settings = self.show_settings.copy()
        new_show_settings[stype] = stream
        show_modal_dialog(
            xmldialogs.SaveStreamSettings,
            "plugin-video-netflix-SaveStreamSettings.xml",
            self.addon.getAddonInfo('path'),
            minutes=0,
            seconds=5,
            new_show_settings=new_show_settings,
            tvshowid=self.current_show,
            storage=self.storage)


    def __str__(self):
        return ('enabled={}, current_show={}'
                .format(self.enabled, self.current_show))
