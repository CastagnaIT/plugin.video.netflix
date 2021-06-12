# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    MSL video profiles

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from resources.lib.globals import G
import resources.lib.common as common

HEVC_M10 = 'hevc-main10-'
CENC_PRK = 'dash-cenc-prk'
CENC_PRK_DO = 'dash-cenc-prk-do'
CENC = 'dash-cenc'
CENC_TL = 'dash-cenc-tl'
HDR = 'hevc-hdr-main10-'
DV5 = 'hevc-dv5-main10-'
VP9_PROFILE0 = 'vp9-profile0-'
# VP9 Profile 2 (HDR) test only, the website does not list it but some videos still have this profile available
# VP9_PROFILE2 = 'vp9-profile2-'

BASE_LEVELS = ['L30-', 'L31-', 'L40-', 'L41-', 'L50-', 'L51-']
VP9_PROFILE0_LEVELS = ['L21-', 'L30-', 'L31-', 'L40-']
# VP9_PROFILE2_LEVELS = ['L30-', 'L31-', 'L40-', 'L50-', 'L51-']


def _profile_strings(base, tails):
    """Creates a list of profile strings by concatenating base with all
    permutations of tails"""
    return [base + level + tail[1] for tail in tails for level in tail[0]]


PROFILES = {
    'base': [
        # Audio
        'heaac-2-dash',
        'heaac-2hq-dash',
        # Unknown
        'BIF240', 'BIF320'],
    'dolbysound': ['ddplus-2.0-dash', 'ddplus-5.1-dash', 'ddplus-5.1hq-dash', 'ddplus-atmos-dash'],
    'h264': ['playready-h264mpl30-dash', 'playready-h264mpl31-dash',
             'playready-h264mpl40-dash',
             'playready-h264hpl22-dash', 'playready-h264hpl30-dash',
             'playready-h264hpl31-dash', 'playready-h264hpl40-dash'],
    'hevc':
        _profile_strings(base=HEVC_M10,
                         tails=[(BASE_LEVELS, CENC),
                                (BASE_LEVELS[:4], CENC_PRK),
                                (BASE_LEVELS, CENC_PRK_DO)]),
    'hdr':
        _profile_strings(base=HDR,
                         tails=[(BASE_LEVELS, CENC),
                                (BASE_LEVELS, CENC_PRK),
                                (BASE_LEVELS, CENC_PRK_DO)]),
    'dolbyvision':
        _profile_strings(base=DV5,
                         tails=[(BASE_LEVELS, CENC_PRK),
                                (BASE_LEVELS, CENC_PRK_DO)]),
    'vp9profile0':
        _profile_strings(base=VP9_PROFILE0,
                         tails=[(VP9_PROFILE0_LEVELS, CENC)])
    # 'vp9profile2':
    #     _profile_strings(base=VP9_PROFILE2,
    #                      tails=[(VP9_PROFILE2_LEVELS, CENC_PRK)])
}


def enabled_profiles():
    """Return a list of all base and enabled additional profiles"""
    return (PROFILES['base'] +
            PROFILES['h264'] +
            _subtitle_profiles() +
            _additional_profiles('vp9profile0', 'enable_vp9_profiles') +
            # _additional_profiles('vp9profile2', 'enable_vp9_profiles') +
            _additional_profiles('dolbysound', 'enable_dolby_sound') +
            _additional_profiles('hevc', 'enable_hevc_profiles') +
            _additional_profiles('hdr',
                                 ['enable_hevc_profiles',
                                  'enable_hdr_profiles']) +
            _additional_profiles('dolbyvision',
                                 ['enable_hevc_profiles',
                                  'enable_dolbyvision_profiles']))


def _subtitle_profiles():
    subtitle_profile = ['webvtt-lssdh-ios8']
    if G.ADDON.getSettingBool('disable_webvtt_subtitle'):
        subtitle_profile = ['simplesdh']
    return subtitle_profile


def _additional_profiles(profiles, req_settings=None, forb_settings=None):
    return (PROFILES[profiles]
            if (all(G.ADDON.getSettingBool(setting) for setting in common.make_list(req_settings)) and
                not any(G.ADDON.getSettingBool(setting) for setting in common.make_list(forb_settings)))
            else [])
