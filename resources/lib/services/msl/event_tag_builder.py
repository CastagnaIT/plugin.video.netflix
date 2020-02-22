# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT (original implementation module)
    Build event tags values

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

from resources.lib import common

AUDIO_CHANNELS_CONV = {1: '1.0', 2: '2.0', 6: '5.1', 8: '7.1'}


def is_media_changed(previous_player_state, player_state):
    """Check if there are variations in player state to avoids overhead processing"""
    if not previous_player_state:
        return True
    # To now we do not check subtitle, because to the moment it is not implemented
    if player_state['currentvideostream'] != previous_player_state['currentvideostream'] or \
            player_state['currentaudiostream'] != previous_player_state['currentaudiostream']:
        return True
    return False


def update_play_times_duration(play_times, player_state):
    """Update the playTimes duration values"""
    duration = player_state['elapsed_seconds'] * 1000
    play_times['total'] = duration
    play_times['audio'][0]['duration'] = duration
    play_times['video'][0]['duration'] = duration


def build_media_tag(player_state, manifest):
    """Build the playTimes and the mediaId data by parsing manifest and the current player streams used"""
    common.fix_locale_languages(manifest['audio_tracks'])
    duration = player_state['elapsed_seconds'] * 1000

    audio_downloadable_id, audio_track_id = _find_audio_data(player_state, manifest)
    video_downloadable_id, video_track_id = _find_video_data(player_state, manifest)
    # Warning 'currentsubtitle' value in player_state on Kodi 18
    # do not have proprieties like isdefault, isforced, isimpaired
    # if in the future the implementation will be done it should be available only on Kodi 19
    # then for now we leave the subtitles as disabled

    text_track_id = 'T:1:1;1;NONE;0;1;'

    play_times = {
        'total': duration,
        'audio': [{
            'downloadableId': audio_downloadable_id,
            'duration': duration
        }],
        'video': [{
            'downloadableId': video_downloadable_id,
            'duration': duration
        }],
        'text': []
    }

    # Format example: "A:1:1;2;en;1;|V:2:1;2;;default;1;CE3;0;|T:1:1;1;NONE;0;1;"
    media_id = '|'.join([audio_track_id, video_track_id, text_track_id])

    return play_times, media_id


def _find_audio_data(player_state, manifest):
    """
    Find the audio downloadable id and the audio track id
    """
    language = common.convert_language_iso(player_state['currentaudiostream']['language'])
    channels = AUDIO_CHANNELS_CONV[player_state['currentaudiostream']['channels']]

    for audio_track in manifest['audio_tracks']:
        if audio_track['language'] == language and audio_track['channels'] == channels:
            # Get the stream dict with the highest bitrate
            stream = max(audio_track['streams'], key=lambda x: x['bitrate'])
            return stream['downloadable_id'], audio_track['new_track_id']
    # Not found?
    raise Exception('build_media_tag: unable to find audio data with language: {}, channels: {}'
                    .format(language, channels))


def _find_video_data(player_state, manifest):
    """
    Find the best match for the video downloadable id and the video track id
    """
    codec = player_state['currentvideostream']['codec']
    width = player_state['currentvideostream']['width']
    height = player_state['currentvideostream']['height']
    for video_track in manifest['video_tracks']:
        for stream in video_track['streams']:
            if codec in stream['content_profile'] and width == stream['res_w'] and height == stream['res_h']:
                return stream['downloadable_id'], video_track['new_track_id']
    # Not found?
    raise Exception('build_media_tag: unable to find video data with codec: {}, width: {}, height: {}'
                    .format(codec, width, height))
