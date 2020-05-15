# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Remember and restore audio stream / subtitle settings between individual episodes of a tv show or movie

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import xbmc

import resources.lib.common as common
from resources.lib.common.cache_utils import CACHE_MANIFESTS
from resources.lib.globals import g
from .action_manager import ActionManager

STREAMS = {
    'audio': {
        'current': 'currentaudiostream',
        'list': 'audiostreams',
        'setter': xbmc.Player.setAudioStream,
    },
    'subtitle': {
        'current': 'currentsubtitle',
        'list': 'subtitles',
        'setter': xbmc.Player.setSubtitleStream,
    },
    'subtitleenabled': {
        'current': 'subtitleenabled',
        'setter': xbmc.Player.showSubtitles
    }
}


class AMStreamContinuity(ActionManager):
    """
    Detects changes in audio / subtitle streams during playback, saves them
    for the currently playing show and restores them on subsequent episodes.
    """

    SETTING_ID = 'StreamContinuityManager_enabled'

    def __init__(self):
        super(AMStreamContinuity, self).__init__()
        self.videoid = None
        self.current_videoid = None
        self.current_streams = {}
        self.sc_settings = {}
        self.player = xbmc.Player()
        self.player_state = {}
        self.resume = {}
        self.legacy_kodi_version = g.KODI_VERSION.is_major_ver('18')
        self.kodi_only_forced_subtitles = None

    def __str__(self):
        return ('enabled={}, current_videoid={}'
                .format(self.enabled, self.current_videoid))

    def initialize(self, data):
        self.videoid = common.VideoId.from_dict(data['videoid'])
        if self.videoid.mediatype not in [common.VideoId.MOVIE, common.VideoId.EPISODE]:
            self.enabled = False
            return
        self.current_videoid = self.videoid \
            if self.videoid.mediatype == common.VideoId.MOVIE \
            else self.videoid.derive_parent(0)
        self.sc_settings = g.SHARED_DB.get_stream_continuity(g.LOCAL_DB.get_active_profile_guid(),
                                                             self.current_videoid.value, {})
        self.kodi_only_forced_subtitles = common.get_kodi_subtitle_language() == 'forced_only'

    def on_playback_started(self, player_state):
        xbmc.sleep(500)  # Wait for slower systems
        self.player_state = player_state
        if self.kodi_only_forced_subtitles and g.ADDON.getSettingBool('forced_subtitle_workaround')\
           and self.sc_settings.get('subtitleenabled') is None:
            # Use the forced subtitle workaround if enabled
            # and if user did not change the subtitle setting
            self._show_only_forced_subtitle()
        for stype in sorted(STREAMS):
            # Save current stream info from the player to local dict
            self._set_current_stream(stype, player_state)
            # Restore the user choice
            self._restore_stream(stype)
        # It is mandatory to wait at least 1 second to allow the Kodi system to update the values
        # changed by restore, otherwise when _on_tick is executed it will save twice unnecessarily
        xbmc.sleep(1000)

    def on_tick(self, player_state):
        self.player_state = player_state
        # Check if the audio stream is changed
        current_stream = self.current_streams['audio']
        player_stream = player_state.get(STREAMS['audio']['current'])
        # If the current audio language is labeled as 'unk' means unknown, skip the save for the next check,
        #   this has been verified on Kodi 18, the cause is unknown
        if player_stream['language'] != 'unk' and not self._is_stream_value_equal(current_stream, player_stream):
            self._set_current_stream('audio', player_state)
            self._save_changed_stream('audio', player_stream)
            common.debug('audio has changed from {} to {}', current_stream, player_stream)

        # Check if subtitle stream or subtitleenabled options are changed
        # Note: Check both at same time, if only one change, is required to save both values,
        #       otherwise Kodi reacts strangely if only one value of these is restored
        current_stream = self.current_streams['subtitle']
        player_stream = player_state.get(STREAMS['subtitle']['current'])
        if not player_stream:
            # I don't know the cause:
            # Very rarely can happen that Kodi starts the playback with the subtitles enabled,
            # but after some seconds subtitles become disabled, and 'currentsubtitle' of player_state data become 'None'
            # Then _is_stream_value_equal() throw error. We do not handle it as a setting change from the user.
            return
        is_sub_stream_equal = self._is_stream_value_equal(current_stream, player_stream)

        current_sub_enabled = self.current_streams['subtitleenabled']
        player_sub_enabled = player_state.get(STREAMS['subtitleenabled']['current'])
        is_sub_enabled_equal = self._is_stream_value_equal(current_sub_enabled, player_sub_enabled)

        if not is_sub_stream_equal or not is_sub_enabled_equal:
            self._set_current_stream('subtitle', player_state)
            self._save_changed_stream('subtitle', player_stream)

            self._set_current_stream('subtitleenabled', player_state)
            self._save_changed_stream('subtitleenabled', player_sub_enabled)
            if not is_sub_stream_equal:
                common.debug('subtitle has changed from {} to {}', current_stream, player_stream)
            if not is_sub_enabled_equal:
                common.debug('subtitleenabled has changed from {} to {}', current_stream,
                             player_stream)

    def _set_current_stream(self, stype, player_state):
        self.current_streams.update({
            stype: player_state.get(STREAMS[stype]['current'])
        })

    def _restore_stream(self, stype):
        set_stream = STREAMS[stype]['setter']
        stored_stream = self.sc_settings.get(stype)
        if stored_stream is None or (isinstance(stored_stream, dict) and not stored_stream):
            return
        common.debug('Trying to restore {} with stored data {}', stype, stored_stream)
        data_type_dict = isinstance(stored_stream, dict)
        if self.legacy_kodi_version:
            # Kodi version 18, this is the old method that have a unresolvable bug:
            # in cases where between episodes there are a number of different streams the
            # audio/subtitle selection fails by setting a wrong language,
            # there is no way with Kodi 18 to compare the streams.
            # will be removed when Kodi 18 is deprecated
            if not self._is_stream_value_equal(self.current_streams[stype], stored_stream):
                # subtitleenabled is boolean and not a dict
                set_stream(self.player, (stored_stream['index']
                                         if data_type_dict
                                         else stored_stream))
        else:
            # Kodi version >= 19, compares stream properties to find the right stream index
            # between episodes with a different numbers of streams
            if not self._is_stream_value_equal(self.current_streams[stype], stored_stream):
                if data_type_dict:
                    index = self._find_stream_index(self.player_state[STREAMS[stype]['list']],
                                                    stored_stream)
                    if index is None:
                        common.debug('No stream match found for {} and {} for videoid {}',
                                     stype, stored_stream, self.current_videoid)
                        return
                    value = index
                else:
                    # subtitleenabled is boolean and not a dict
                    value = stored_stream
                set_stream(self.player, value)
        self.current_streams[stype] = stored_stream
        common.debug('Restored {} to {}', stype, stored_stream)

    def _save_changed_stream(self, stype, stream):
        common.debug('Save changed stream {} for {}', stream, stype)
        self.sc_settings[stype] = stream
        g.SHARED_DB.set_stream_continuity(g.LOCAL_DB.get_active_profile_guid(),
                                          self.current_videoid.value,
                                          self.sc_settings)

    def _find_stream_index(self, streams, stored_stream):
        """
        Find the right stream index
        --- THIS WORKS ONLY WITH KODI VERSION 19 AND UP
        in the case of episodes, it is possible that between different episodes some languages are
        not present, so the indexes are changed, then you have to rely on the streams properties
        """
        language = stored_stream['language']
        channels = stored_stream.get('channels')
        # is_default = stored_stream.get('isdefault')
        # is_original = stored_stream.get('isoriginal')
        is_impaired = stored_stream.get('isimpaired')
        is_forced = stored_stream.get('isforced')

        # Filter streams by language
        streams = _filter_streams(streams, 'language', language)

        # Filter streams by number of channel (on audio stream)
        if channels:
            for n_channels in range(channels, 3, -1):  # Auto fallback on fewer channels
                results = _filter_streams(streams, 'channels', n_channels)
                if results:
                    streams = results
                    break

        # Find the impaired stream
        if is_impaired:
            for stream in streams:
                if stream.get('isimpaired'):
                    return stream['index']
        else:
            # Remove impaired streams
            streams = _filter_streams(streams, 'isimpaired', False)

        # Find the forced stream (on subtitle stream)
        if is_forced:
            for stream in streams:
                if stream.get('isforced'):
                    return stream['index']
            # Forced stream not found, then fix Kodi bug if user chose to apply the workaround
            # Kodi bug???:
            # If the kodi player is set with "forced only" subtitle setting, Kodi use this behavior:
            # 1) try to select forced subtitle that matches audio language
            # 2) if missing the forced subtitle in language, then
            #    Kodi try to select: The first "forced" subtitle or the first "regular" subtitle
            #    that can respect the chosen language or not, depends on the available streams
            # So can cause a wrong subtitle language or in a permanent display of subtitles!
            # This does not reflect the setting chosen in the Kodi player and is very annoying!
            # There is no other solution than to disable the subtitles manually.
            if g.ADDON.getSettingBool('forced_subtitle_workaround') and \
               self.kodi_only_forced_subtitles:
                # Note: this change is temporary so not stored to db by sc_settings setter
                self.sc_settings.update({'subtitleenabled': False})
                return None
        else:
            # Remove forced streams
            streams = _filter_streams(streams, 'isforced', False)

        # if the language is not missing there should be at least one result
        return streams[0]['index'] if streams else None

    def _show_only_forced_subtitle(self):
        # Forced stream not found, then fix Kodi bug if user chose to apply the workaround
        # Kodi bug???:
        # If the kodi player is set with "forced only" subtitle setting, Kodi use this behavior:
        # 1) try to select forced subtitle that matches audio language
        # 2) if missing the forced subtitle in language, then
        #    Kodi try to select: The first "forced" subtitle or the first "regular" subtitle
        #    that can respect the chosen language or not, depends on the available streams
        # So can cause a wrong subtitle language or in a permanent display of subtitles!
        # This does not reflect the setting chosen in the Kodi player and is very annoying!
        # There is no other solution than to disable the subtitles manually.
        audio_language = common.get_kodi_audio_language()
        if self.legacy_kodi_version:
            # --- ONLY FOR KODI VERSION 18 ---
            # NOTE: With Kodi 18 it is not possible to read the properties of the streams
            # so the only possible way is to read the data from the manifest file
            cache_identifier = g.get_esn() + '_' + self.videoid.value
            manifest_data = g.CACHE.get(CACHE_MANIFESTS, cache_identifier)
            common.fix_locale_languages(manifest_data['timedtexttracks'])
            if not any(text_track.get('isForcedNarrative', False) is True and
                       text_track['language'] == audio_language
                       for text_track in manifest_data['timedtexttracks']):
                self.sc_settings.update({'subtitleenabled': False})
        else:
            # --- ONLY FOR KODI VERSION 19 ---
            # Check the current stream
            player_stream = self.player_state.get(STREAMS['subtitle']['current'])
            if not player_stream['isforced'] or player_stream['language'] != audio_language:
                self.sc_settings.update({'subtitleenabled': False})

    def _is_stream_value_equal(self, stream_a, stream_b):
        if self.legacy_kodi_version:
            # Kodi version 18, compare dict values directly, this will always fails when
            # between episodes the number of streams change,
            # there is no way with Kodi 18 to compare the streams
            # will be removed when Kodi 18 is deprecated
            return stream_a == stream_b
        # Kodi version >= 19, compares stream properties to find the right stream index
        # between episodes with a different numbers of streams
        if isinstance(stream_a, dict):
            return common.compare_dicts(stream_a, stream_b, ['index'])
        # subtitleenabled is boolean and not a dict
        return stream_a == stream_b


def _filter_streams(streams, filter_name, match_value):
    return [dict_stream for dict_stream in streams if
            dict_stream.get(filter_name, False) == match_value]
