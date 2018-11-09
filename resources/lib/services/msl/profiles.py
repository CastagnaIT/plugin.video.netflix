# -*- coding: utf-8 -*-
"""MSL video profiles"""
from __future__ import unicode_literals

import xbmcaddon

from resources.lib.globals import g

HEVC = 'hevc-main-'
HEVC_M10 = 'hevc-main10-'
CENC_PRK = 'dash-cenc-prk'
CENC = 'dash-cenc'
CENC_TL = 'dash-cenc-tl'
HDR = 'hevc-hdr-main10-'
DV = 'hevc-dv-main10-'
DV5 = 'hevc-dv5-main10-'

BASE_LEVELS = ['L30-', 'L31-', 'L40-', 'L41-', 'L50-', 'L51-']
CENC_TL_LEVELS = ['L30-L31-', 'L31-L40-', 'L40-L41-', 'L50-L51-']


def _profile_strings(base, tails):
    """Creates a list of profile strings by concatenating base with all
    permutations of tails"""
    return [base + level + tail[1] for tail in tails for level in tail[0]]


PROFILES = {
    'base': [
        # Video
        'playready-h264bpl30-dash', 'playready-h264mpl30-dash',
        'playready-h264mpl31-dash', 'playready-h264mpl40-dash',
        # Audio
        'heaac-2-dash',
        'heaac-5.1-dash',
        # Subtiltes
        # 'dfxp-ls-sdh',
        # 'simplesdh',
        # 'nflx-cmisc',
        # Unkown
        'BIF240', 'BIF320'],
    'dolbysound': ['ddplus-2.0-dash', 'ddplus-5.1-dash'],
    'atmos': ['ddplus-atmos-dash'],
    'hevc':
        _profile_strings(base=HEVC,
                         tails=[(BASE_LEVELS, CENC),
                                (CENC_TL_LEVELS, CENC_TL)]) +
        _profile_strings(base=HEVC_M10,
                         tails=[(BASE_LEVELS, CENC),
                                (BASE_LEVELS[:4], CENC_PRK),
                                (CENC_TL_LEVELS, CENC_TL)]),
    'hdr':
        _profile_strings(base=HDR,
                         tails=[(BASE_LEVELS, CENC),
                                (BASE_LEVELS, CENC_PRK)]),
    'dolbyvision':
        _profile_strings(base=DV,
                         tails=[(BASE_LEVELS, CENC)]) +
        _profile_strings(base=DV5,
                         tails=[(BASE_LEVELS, CENC_PRK)]),
    'vp9': ['vp9-profile0-L30-dash-cenc', 'vp9-profile0-L31-dash-cenc']
}


def enabled_profiles():
    """Return a list of all base and enabled additional profiles"""
    return (PROFILES['base'] +
            _subtitle_profiles() +
            _additional_profiles('dolbysound', 'enable_dolby_sound') +
            _additional_profiles('atmos', 'enable_atmos_sound') +
            _additional_profiles('hevc', 'enable_hevc_profiles') +
            _additional_profiles('hdr',
                                 ['enable_hevc_profiles',
                                  'enable_hdr_profiles']) +
            _additional_profiles('dolbyvision',
                                 ['enable_hevc_profiles',
                                  'enable_dolbyvision_profiles']) +
            _vp9_profiles())


def _subtitle_profiles():
    inputstream_addon = xbmcaddon.Addon('inputstream.adaptive')
    return ['webvtt-lssdh-ios8'
            if inputstream_addon.getAddonInfo('version') >= '2.3.8'
            else 'simplesdh']


def _additional_profiles(profiles, settings):
    settings = settings if isinstance(settings, list) else [settings]
    return (PROFILES[profiles]
            if all(g.ADDON.getSettingBool(setting) for setting in settings)
            else [])


def _vp9_profiles():
    return (PROFILES['vp9']
            if (not g.ADDON.getSettingBool('enable_hevc_profiles') or
                g.ADDON.getSettingBool('enable_vp9_profiles'))
            else [])
