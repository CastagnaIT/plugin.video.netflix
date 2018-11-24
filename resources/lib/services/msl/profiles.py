# -*- coding: utf-8 -*-
"""MSL video profiles"""
from __future__ import unicode_literals

import xbmcaddon

from resources.lib.globals import g
import resources.lib.common as common

HEVC = 'hevc-main-'
HEVC_M10 = 'hevc-main10-'
CENC_PRK = 'dash-cenc-prk'
CENC = 'dash-cenc'
CENC_TL = 'dash-cenc-ctl'
HDR = 'hevc-hdr-main10-'
DV = 'hevc-dv-main10-'
DV5 = 'hevc-dv5-main10-'
VP9 = 'vp9-profile0-'

BASE_LEVELS = ['L30-', 'L31-', 'L40-', 'L41-', 'L50-', 'L51-']
CENC_TL_LEVELS = ['L30-L31-', 'L31-L40-', 'L40-L41-', 'L50-L51-']


def _profile_strings(base, tails):
    """Creates a list of profile strings by concatenating base with all
    permutations of tails"""
    return [base + level + tail[1] for tail in tails for level in tail[0]]


PROFILES = {
    'base': [
        # Audio
        'heaac-2-dash',
        # Unkown
        'BIF240', 'BIF320'],
    'dolbysound': ['ddplus-2.0-dash', 'ddplus-5.1-dash', 'ddplus-5.1hq-dash',
                   'ddplus-atmos-dash'],
    'h264': ['playready-h264mpl30-dash', 'playready-h264mpl31-dash',
             'playready-h264mpl40-dash', 'playready-h264mpl41-dash'],
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
    'vp9':
        _profile_strings(base=VP9,
                         tails=[(BASE_LEVELS, CENC)])
}


def enabled_profiles():
    """Return a list of all base and enabled additional profiles"""
    return (PROFILES['base'] +
            PROFILES['h264'] +
            _subtitle_profiles() +
            _additional_profiles('vp9', forb_settings='enable_hevc_profiles') +
            _additional_profiles('dolbysound', 'enable_dolby_sound') +
            _additional_profiles('hevc', 'enable_hevc_profiles') +
            _additional_profiles('hdr',
                                 ['enable_hevc_profiles',
                                  'enable_hdr_profiles']) +
            _additional_profiles('dolbyvision',
                                 ['enable_hevc_profiles',
                                  'enable_dolbyvision_profiles']))


def _subtitle_profiles():
    isversion = xbmcaddon.Addon('inputstream.adaptive').getAddonInfo('version')
    return ['webvtt-lssdh-ios8'
            if common.is_minimum_version(isversion, '2.3.8')
            else 'simplesdh']


def _additional_profiles(profiles, req_settings=None, forb_settings=None):
    return (PROFILES[profiles]
            if (all(g.ADDON.getSettingBool(setting)
                for setting in common.make_list(req_settings)) and
                not (any(g.ADDON.getSettingBool(setting)
                     for setting in common.make_list(forb_settings))))
            else [])
