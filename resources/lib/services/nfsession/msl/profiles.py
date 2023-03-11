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
CENC_PRK_QC = 'dash-cenc-prk-qc'
CENC_PRK_DO = 'dash-cenc-prk-do'
CENC = 'dash-cenc'
CENC_TL = 'dash-cenc-tl'
CBCS_PRK = 'dash-cbcs-prk'
HDR = 'hevc-hdr-main10-'
DV5 = 'hevc-dv5-main10-'
VP9_PROFILE0 = 'vp9-profile0-'
# VP9 Profile 2 (10/12 bit color depth) the website does not list it but some videos still have this profile available
VP9_PROFILE2 = 'vp9-profile2-'
AV1 = 'av1-main-'

# Video codec levels
LEVELS_2 = ['L20-', 'L21-']
LEVELS_3 = ['L30-', 'L31-']
LEVELS_4 = ['L40-', 'L41-']
LEVELS_5 = ['L50-', 'L51-']
ALL_LEVELS = LEVELS_2 + LEVELS_3 + LEVELS_4 + LEVELS_5


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
    'h264_prk_qc': ['h264mpl30-dash-playready-prk-qc', 'h264mpl31-dash-playready-prk-qc',
                    'h264mpl40-dash-playready-prk-qc'],
    'hevc':
        _profile_strings(base=HEVC_M10,
                         tails=[(LEVELS_3 + LEVELS_4 + LEVELS_5, CENC),
                                (LEVELS_3 + LEVELS_4, CENC_PRK),
                                (LEVELS_3 + LEVELS_4 + LEVELS_5, CENC_PRK_DO)]),
    'hdr':
        _profile_strings(base=HDR,
                         tails=[(LEVELS_3 + LEVELS_4 + LEVELS_5, CENC_PRK),
                                (LEVELS_3 + LEVELS_4 + LEVELS_5, CENC_PRK_DO)]),
    'dolbyvision':
        _profile_strings(base=DV5,
                         tails=[(LEVELS_3 + LEVELS_4 + LEVELS_5, CENC_PRK),
                                (LEVELS_4 + LEVELS_5, CENC_PRK_QC),
                                (LEVELS_3 + LEVELS_4 + LEVELS_5, CENC_PRK_DO)]),
    'vp9profile0':
        _profile_strings(base=VP9_PROFILE0,
                         tails=[(LEVELS_2[1:2] + LEVELS_3 + LEVELS_4[:1], CENC)]),
    'vp9profile2':
        _profile_strings(base=VP9_PROFILE2,
                         tails=[(LEVELS_3 + LEVELS_4[:1] + LEVELS_5, CENC_PRK)]),
    'av1':
        _profile_strings(base=AV1,
                         tails=[(ALL_LEVELS, CBCS_PRK)])
}


def enabled_profiles():
    """Return a list of all base and enabled additional profiles"""
    return (PROFILES['base'] +
            PROFILES['h264'] + PROFILES['h264_prk_qc'] +
            _subtitle_profiles() +
            _additional_profiles('vp9profile0', 'enable_vp9_profiles') +
            _additional_profiles('vp9profile2', ['enable_vp9_profiles', 'enable_vp9.2_profiles']) +
            _additional_profiles('dolbysound', 'enable_dolby_sound') +
            _additional_profiles('hevc', 'enable_hevc_profiles') +
            _additional_profiles('hdr', ['enable_hevc_profiles', 'enable_hdr_profiles']) +
            _additional_profiles('dolbyvision', ['enable_hevc_profiles', 'enable_dolbyvision_profiles']) +
            _additional_profiles('av1', 'enable_av1_profiles'))


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
