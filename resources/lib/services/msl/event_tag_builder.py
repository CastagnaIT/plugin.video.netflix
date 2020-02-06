# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT (original implementation module)
    Build event tags values

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals


def get_media_id(videoid, player_state, manifest):
    """Try to build the mediaId by parsing manifest with the current player streams used"""
    # Build using 'new_track_id' tags
    # Format example: "A:1:1;2;en;1;|V:2:1;2;;default;1;CE3;0;|T:1:1;1;NONE;0;1;"
    return manifest['defaultTrackOrderList'][0]['mediaId']  # Todo: test purpose


def get_play_times(videoid, player_state, manifest):
    """Build the playTimes dict by parsing manifest with the current player streams used"""
    duration = player_state['elapsed_seconds'] * 1000

    # Todo: elaborate from manifest
    audio_downloadable_id = manifest['audio_tracks'][0]['streams'][0]['downloadable_id']  # Todo: test purpose
    video_downloadable_id = manifest['video_tracks'][0]['streams'][0]['downloadable_id']  # Todo: test purpose

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
    return play_times
