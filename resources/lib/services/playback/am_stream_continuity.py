# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Remember and restore audio stream / subtitle settings between individual episodes of a tv show or movie
    Change the default Kodi behavior of subtitles according to user customizations

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import copy

import xbmc

import resources.lib.common as common
from resources.lib.globals import G
from resources.lib.kodi import ui
from resources.lib.utils.logging import LOG
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
    Detects changes in audio / subtitle streams during playback and saves them to restore them later,
    Change the default Kodi behavior of subtitles according to user customizations
    """
    # How test/debug these features:
    # First thing (if not needed to your debug) disable "Remember audio / subtitle preferences" feature.
    # When you play a video, and you try to change audio/subtitles tracks, Kodi may save this change in his database,
    # the same thing happen when you use/enable the features of this module.
    # So when the next time you play the SAME video may invalidate these features, because Kodi restore saved settings.
    # To test multiple times these features on the SAME video, (e.g.),
    # you must delete, every time, the file /Kodi/userdata/Database/MyVideosXXX.db, or,
    # if you are able you can delete in realtime the data in the 'settings' table of db file.
    def __init__(self):
        super().__init__()
        self.enabled = True  # By default we enable this action manager
        self.current_streams = {}
        self.sc_settings = {}
        self.player = xbmc.Player()
        self.player_state = {}
        self.resume = {}
        self.is_kodi_forced_subtitles_only = None
        self.is_prefer_alternative_lang = None

    def __str__(self):
        return f'enabled={self.enabled}, videoid_parent={self.videoid_parent}'

    def initialize(self, data):
        self.is_kodi_forced_subtitles_only = common.get_kodi_subtitle_language() == 'forced_only'
        self.is_prefer_alternative_lang = G.ADDON.getSettingBool('prefer_alternative_lang')

    def on_playback_started(self, player_state):
        is_enabled = G.ADDON.getSettingBool('StreamContinuityManager_enabled')
        if is_enabled:
            # Get user saved preferences
            self.sc_settings = G.SHARED_DB.get_stream_continuity(G.LOCAL_DB.get_active_profile_guid(),
                                                                 self.videoid_parent.value, {})
        else:
            # Disable on_tick activity to check changes of settings
            self.enabled = False
        if (player_state.get(STREAMS['subtitle']['current']) is None and
                player_state.get('currentvideostream') is None):
            # Kodi 19 BUG JSON RPC: "Player.GetProperties" is broken: https://github.com/xbmc/xbmc/issues/17915
            # The first call return wrong data the following calls return OSError, and then _notify_all will be blocked
            self.enabled = False
            LOG.error('Due of Kodi 19 bug has been disabled: '
                      'Ask to skip dialog, remember audio/subtitles preferences and other features')
            ui.show_notification(title=common.get_local_string(30105),
                                 msg='Due to Kodi bug has been disabled all Netflix features')
            return
        xbmc.sleep(500)  # Wait for slower systems
        self.player_state = player_state
        # If the user has not changed the subtitle settings
        if self.sc_settings.get('subtitleenabled') is None:
            # Copy player state to restore it after, or the changes will affect the _restore_stream()
            _player_state_copy = copy.deepcopy(player_state)
            # Force selection of the audio/subtitles language with country code
            if self.is_prefer_alternative_lang:
                self._select_lang_with_country_code()
            # Ensures the display of forced subtitles only with the audio language set
            if G.ADDON.getSettingBool('show_forced_subtitles_only'):
                self._ensure_forced_subtitle_only()
            # Ensure in any case to show the regular subtitles when the preferred audio language is not available
            if G.ADDON.getSettingBool('show_subtitles_miss_audio'):
                self._ensure_subtitles_no_audio_available()
            player_state = _player_state_copy
        for stype in sorted(STREAMS):
            # Save current stream setting from the Kodi player to the local dict
            self._set_current_stream(stype, player_state)
            # Apply the chosen stream setting to Kodi player and update the local dict
            self._restore_stream(stype)
        if is_enabled:
            # It is mandatory to wait at least 1 second to allow the Kodi system to update the values
            # changed by restore, otherwise when on_tick is executed it will save twice unnecessarily
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
            LOG.debug('audio has changed from {} to {}', current_stream, player_stream)

        # Check if subtitle stream or subtitleenabled options are changed
        # Note: Check both at same time, if only one change, is required to save both values,
        #       otherwise Kodi reacts strangely if only one value of these is restored
        current_stream = self.current_streams['subtitle']
        player_stream = player_state.get(STREAMS['subtitle']['current'])
        if not player_stream:
            # Manage case of no subtitles, and an issue:
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
                LOG.debug('subtitle has changed from {} to {}', current_stream, player_stream)
            if not is_sub_enabled_equal:
                LOG.debug('subtitleenabled has changed from {} to {}', current_stream, player_stream)

    def _set_current_stream(self, stype, player_state):
        self.current_streams.update({
            stype: player_state.get(STREAMS[stype]['current'])
        })

    def _restore_stream(self, stype):
        set_stream = STREAMS[stype]['setter']
        stored_stream = self.sc_settings.get(stype)
        if stored_stream is None or (isinstance(stored_stream, dict) and not stored_stream):
            return
        LOG.debug('Trying to restore {} with stored data {}', stype, stored_stream)
        data_type_dict = isinstance(stored_stream, dict)
        # Compares stream properties to find the right stream index
        # between episodes with a different numbers of streams
        if not self._is_stream_value_equal(self.current_streams[stype], stored_stream):
            if data_type_dict:
                index = self._find_stream_index(self.player_state[STREAMS[stype]['list']],
                                                stored_stream)
                if index is None:
                    LOG.debug('No stream match found for {} and {} for videoid {}',
                              stype, stored_stream, self.videoid_parent)
                    return
                value = index
            else:
                # subtitleenabled is boolean and not a dict
                value = stored_stream
            set_stream(self.player, value)
        self.current_streams[stype] = stored_stream
        LOG.debug('Restored {} to {}', stype, stored_stream)

    def _save_changed_stream(self, stype, stream):
        LOG.debug('Save changed stream {} for {}', stream, stype)
        self.sc_settings[stype] = stream
        G.SHARED_DB.set_stream_continuity(G.LOCAL_DB.get_active_profile_guid(),
                                          self.videoid_parent.value,
                                          self.sc_settings)

    def _find_stream_index(self, streams, stored_stream):
        """
        Find the right stream index
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
            # Note: this change is temporary so not stored to db by sc_settings setter
            self.sc_settings.update({'subtitleenabled': False})
            return None
        # Remove forced streams
        streams = _filter_streams(streams, 'isforced', False)
        # if the language is not missing there should be at least one result
        return streams[0]['index'] if streams else None

    def _select_lang_with_country_code(self):
        """Force selection of the audio/subtitles language with country code"""
        # --- Audio side ---
        # NOTE: Kodi is able to auto-select the language with country code for audio/subtitles only
        # if audio track is set as default and the Kodi Player audio language is set as "mediadefault".
        pref_audio_language = self._get_preferred_audio_language()
        # Get current audio languages
        audio_list = self.player_state.get(STREAMS['audio']['list'])
        lang_code = _find_lang_with_country_code(audio_list, pref_audio_language)
        if lang_code and common.get_kodi_audio_language() not in ['mediadefault', 'original']:
            stream_audio = None
            if common.get_kodi_is_prefer_audio_impaired():
                stream_audio = next((audio_track for audio_track in audio_list
                                     if audio_track['language'] == lang_code
                                     and audio_track['isimpaired']
                                     and audio_track['isdefault']),  # The default track can change is user choose 2ch
                                    None)
            if not stream_audio:
                stream_audio = next((audio_track for audio_track in audio_list
                                     if audio_track['language'] == lang_code
                                     and not audio_track['isimpaired']
                                     and audio_track['isdefault']),  # The default track can change is user choose 2ch
                                    None)
            if stream_audio:
                self.sc_settings.update({'audio': stream_audio})
                # We update the current player state data to avoid wrong behaviour with features executed after
                self.player_state[STREAMS['audio']['current']] = stream_audio
        # --- Subtitles side ---
        # Get the subtitles language set in Kodi Player setting
        pref_subtitle_language = self._get_preferred_subtitle_language()
        if not pref_subtitle_language:
            return
        subtitle_list = self.player_state.get(STREAMS['subtitle']['list'])
        lang_code = _find_lang_with_country_code(subtitle_list, pref_subtitle_language)
        if not lang_code:
            return
        stream_sub = self._find_subtitle_stream(lang_code, self.is_kodi_forced_subtitles_only)
        if stream_sub:
            self.sc_settings.update({'subtitleenabled': True})
            self.sc_settings.update({'subtitle': stream_sub})
            # We update the current player state data to avoid wrong behaviour with features executed after
            self.player_state[STREAMS['subtitle']['current']] = stream_sub

    def _ensure_forced_subtitle_only(self):
        """Ensures the display of forced subtitles only with the preferred audio language set"""
        # When the audio language in Kodi player is set e.g. to 'Italian', and you try to play a video
        # without Italian audio language, Kodi choose another language available e.g. English,
        # this will also be reflected on the subtitles that which will be shown in English language,
        # but the subtitles may be available in Italian or the user may not want to view them in other languages.
        # Get current subtitle stream set (could be also changed by _select_lang_with_country_code)
        sub_stream = self.player_state.get(STREAMS['subtitle']['current'])
        if not sub_stream:
            return
        # Get the preferred audio language
        pref_audio_language = self._get_preferred_audio_language()
        # Get current audio languages
        audio_list = self.player_state.get(STREAMS['audio']['list'])
        if self.is_prefer_alternative_lang:
            lang_code = _find_lang_with_country_code(audio_list, pref_audio_language)
            if lang_code:
                pref_audio_language = lang_code
        if '-' not in pref_audio_language:
            pref_audio_language = common.convert_language_iso(pref_audio_language, xbmc.ISO_639_2)
        if sub_stream['isforced'] and sub_stream['language'] == pref_audio_language:
            return
        subtitles_list = self.player_state.get(STREAMS['subtitle']['list'])
        if not sub_stream['language'] == pref_audio_language:
            # The current subtitle is not forced or forced but not in the preferred audio language
            # Try find a forced subtitle in the preferred audio language
            stream = next((subtitle_track for subtitle_track in subtitles_list
                           if subtitle_track['language'] == pref_audio_language
                           and subtitle_track['isforced']),
                          None)
            if stream:
                # Set the forced subtitle
                self.sc_settings.update({'subtitleenabled': True})
                self.sc_settings.update({'subtitle': stream})
            else:
                # Disable the subtitles
                self.sc_settings.update({'subtitleenabled': False})

    def _ensure_subtitles_no_audio_available(self):
        """Ensure in any case to show the regular subtitles when the preferred audio language is not available"""
        # Check if there are subtitles
        subtitles_list = self.player_state.get(STREAMS['subtitle']['list'])
        if not subtitles_list:
            return
        # Get the preferred audio language
        pref_audio_language = self._get_preferred_audio_language()
        audio_list = self.player_state.get(STREAMS['audio']['list'])
        # Check if there is an audio track available in the preferred audio language,
        # can also happen that in list there are languages with country code only
        accepted_lang_codes = [common.convert_language_iso(pref_audio_language, xbmc.ISO_639_2)]
        if self.is_prefer_alternative_lang:
            lang_code = _find_lang_with_country_code(audio_list, pref_audio_language)
            if lang_code:
                accepted_lang_codes.append(lang_code)
        stream = None
        if not any(audio_track['language'] in accepted_lang_codes for audio_track in audio_list):
            # No audio available in the preferred audio languages,
            # then try find a regular subtitle in the preferred audio language
            if len(accepted_lang_codes) == 2:
                # Try find with country code
                stream = self._find_subtitle_stream(accepted_lang_codes[-1])
            if not stream:
                stream = self._find_subtitle_stream(accepted_lang_codes[0])
        if stream:
            self.sc_settings.update({'subtitleenabled': True})
            self.sc_settings.update({'subtitle': stream})

    def _find_subtitle_stream(self, language, is_forced=False):
        # Take in account if a user have enabled Kodi impaired subtitles preference
        # but only without forced setting (same Kodi player behaviour)
        is_prefer_impaired = common.get_kodi_is_prefer_sub_impaired() and not is_forced
        subtitles_list = self.player_state.get(STREAMS['subtitle']['list'])
        stream = None
        if is_prefer_impaired:
            stream = next((subtitle_track for subtitle_track in subtitles_list
                           if subtitle_track['language'] == language
                           and subtitle_track['isforced'] == is_forced
                           and subtitle_track['isimpaired']),
                          None)
        if not stream:
            stream = next((subtitle_track for subtitle_track in subtitles_list
                           if subtitle_track['language'] == language
                           and subtitle_track['isforced'] == is_forced
                           and not subtitle_track['isimpaired']),
                          None)
        return stream

    def _get_preferred_audio_language(self):
        """
        Get the language code of the preferred audio as set in Kodi Player setting
        :return: The language code (as ISO with 2 letters)
        """
        audio_language = common.get_kodi_audio_language()
        if audio_language == 'mediadefault':
            # Netflix do not have a "Media default" track then we rely on the language of current nf profile,
            # although due to current Kodi locale problems could be not always accurate.
            profile_language_code = G.LOCAL_DB.get_profile_config('language')
            audio_language = profile_language_code[:2]
        if audio_language == 'original':
            # Get current audio languages
            audio_list = self.player_state.get(STREAMS['audio']['list'])
            # Find the language of the original audio track
            stream = next((audio_track for audio_track in audio_list if audio_track['isoriginal']), None)
            # stream['language'] can be ISO 3 letters or with country code (pt-BR) / converted with LOCALE_CONV_TABLE
            if stream is None:  # Means some problem, let the code break
                audio_language = None
            else:
                if '-' in stream['language']:
                    audio_language = stream['language'][:2]
                else:
                    audio_language = common.convert_language_iso(stream['language'])
        return audio_language

    def _get_preferred_subtitle_language(self):
        """
        Get the language code of the preferred subtitle as set in Kodi Player setting
        :return: The language code (as ISO with 2 letters) or 'None' if disabled
        """
        subtitle_language = common.get_kodi_subtitle_language()
        if subtitle_language == 'forced_only':
            # Then match the audio language
            subtitle_language = self._get_preferred_audio_language()
        elif subtitle_language == 'original':
            # Get current audio languages
            audio_list = self.player_state.get(STREAMS['audio']['list'])
            # Find the language of the original audio track
            stream = next((audio_track for audio_track in audio_list if audio_track['isoriginal']), None)
            # stream['language'] can be ISO 3 letters or with country code (pt-BR) / converted with LOCALE_CONV_TABLE
            if stream is None:
                subtitle_language = None
            else:
                if '-' in stream['language']:
                    subtitle_language = stream['language'][:2]
                else:
                    subtitle_language = common.convert_language_iso(stream['language'])
        elif subtitle_language == 'default':
            # Get the Kodi UI language
            subtitle_language = common.get_kodi_ui_language()
        elif subtitle_language == 'none':
            # Subtitles are disabled
            subtitle_language = None
        return subtitle_language

    def _is_stream_value_equal(self, stream_a, stream_b):
        if isinstance(stream_a, dict):
            return common.compare_dict_keys(stream_a, stream_b,
                                            ['channels', 'codec', 'isdefault', 'isimpaired', 'isoriginal', 'language'])
        # subtitleenabled is boolean and not a dict
        return stream_a == stream_b


def _filter_streams(streams, filter_name, match_value):
    return [dict_stream for dict_stream in streams if
            dict_stream.get(filter_name, False) == match_value]


def _find_lang_with_country_code(tracks_list, lang_code):
    """
    Try to find a language code with country code
    :param tracks_list: list of tracks where search the language code
    :param lang_code: the language code to find (2 letters - ISO_639_1)
    :return: the language code with country code or 'None' if it does not exist
    """
    # The search checks whether a language exists with "-" char.
    # Usually for the same language there might be two different countries,
    # e.g. "es" and "es-ES" (that will be converted in "es-Spain" by LOCALE_CONV_TABLE)
    _stream = next((track for track in tracks_list
                    if track['language'].startswith(lang_code + '-')), None)
    if _stream:
        return _stream['language']
    return None
