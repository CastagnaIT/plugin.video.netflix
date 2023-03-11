# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2020 Stefano Gottardo - @CastagnaIT (original implementation module)
    Add-on configuration wizard

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import inputstreamhelper
from xbmc import getCondVisibility
from xbmcaddon import Addon
from xbmcgui import getScreenHeight, getScreenWidth

from resources.lib.common import (get_system_platform, is_device_4k_capable, get_local_string, json_rpc,
                                  get_supported_hdr_types, get_android_system_props)
from resources.lib.common.exceptions import InputStreamHelperError
from resources.lib.globals import G
from resources.lib.kodi.ui import show_ok_dialog, ask_for_confirmation
from resources.lib.utils.logging import LOG


def run_addon_configuration(restore=False):
    """
    Add-on configuration wizard,
    automatically configures profiles and add-ons dependencies, based on user-supplied data and device characteristics
    and restore to default some expert settings when requested
    """
    LOG.debug('Running add-on configuration wizard')
    _set_codec_profiles()
    _set_kodi_settings()
    _set_isa_addon_settings(get_system_platform() == 'android')

    # Restore default settings that may have been misconfigured by the user
    if restore:
        G.ADDON.setSettingString('isa_streamselection_override', 'disabled')
        G.ADDON.setSettingString('stream_max_resolution', '--')
        G.ADDON.setSettingString('stream_force_hdcp', '--')
        G.ADDON.setSettingString('msl_manifest_version', 'default')
        G.ADDON.setSettingString('cdn_server', 'Server 1')

    # Enable UpNext if it is installed and enabled
    G.ADDON.setSettingBool('UpNextNotifier_enabled', getCondVisibility('System.AddonIsEnabled(service.upnext)'))
    if restore:
        show_ok_dialog(get_local_string(30154), get_local_string(30157))


def _set_isa_addon_settings(hdcp_override):
    """Method for self-configuring of InputStream Adaptive add-on"""
    try:
        is_helper = inputstreamhelper.Helper('mpd')
        if not is_helper.check_inputstream():
            show_ok_dialog(get_local_string(30154), get_local_string(30046))
            return
    except Exception as exc:  # pylint: disable=broad-except
        # Captures all types of ISH internal errors
        import traceback
        LOG.error(traceback.format_exc())
        raise InputStreamHelperError(str(exc)) from exc

    if G.KODI_VERSION < '20':
        # Only needed for Kodi <= v19, this has been fixed on Kodi 20
        isa_addon = Addon('inputstream.adaptive')
        isa_addon.setSettingBool('HDCPOVERRIDE', hdcp_override)
        if isa_addon.getSettingInt('STREAMSELECTION') == 1:
            # Stream selection must never be set to 'Manual' or cause problems with the streams
            isa_addon.setSettingInt('STREAMSELECTION', 0)
        # 'Ignore display' should only be set when Kodi display resolution is not 4K
        isa_addon.setSettingBool('IGNOREDISPLAY',
                                 is_device_4k_capable() and (getScreenWidth() != 3840 or getScreenHeight() != 2160))


def _set_codec_profiles():
    """Method for self-configuring of netflix manifest codec profiles"""
    enable_vp9_profiles = True
    enable_hevc_profiles = False
    if get_system_platform() == 'android':
        # We cannot determine the codecs supported by the device in advance so...
        # ...we do not enable VP9 because many older mobile devices do not support it
        enable_vp9_profiles = False
        # ...we enable HEVC by default on tv boxes and 4K capable devices
        is_android_tv = 'TV' in get_android_system_props().get('ro.build.characteristics', '').upper()
        enable_hevc_profiles = is_android_tv or is_device_4k_capable()
        # Get supported HDR types by the display (configuration works from Kodi v20)
        supported_hdr_types = get_supported_hdr_types()
        if supported_hdr_types and enable_hevc_profiles: # for now only HEVC have HDR/DV
            is_hdr10_enabled = False
            is_dv_enabled = False
            # Ask to enable HDR10
            if 'hdr10' in supported_hdr_types:
                is_hdr10_enabled = ask_for_confirmation('Netflix', get_local_string(30742))
            # Ask to enable Dolby Vision
            if is_hdr10_enabled and 'dolbyvision' in supported_hdr_types:
                is_dv_enabled = ask_for_confirmation('Netflix', get_local_string(30743))
            G.ADDON.setSettingBool('enable_hdr_profiles', is_hdr10_enabled)
            G.ADDON.setSettingBool('enable_dolbyvision_profiles', is_dv_enabled)
    G.ADDON.setSettingBool('enable_vp9_profiles', enable_vp9_profiles)
    G.ADDON.setSettingBool('enable_vp9.2_profiles', False)
    G.ADDON.setSettingBool('enable_hevc_profiles', enable_hevc_profiles)
    G.ADDON.setSettingBool('enable_av1_profiles', False)
    G.ADDON.setSettingBool('disable_webvtt_subtitle', False)


def _set_kodi_settings():
    """Method for self-configuring Kodi settings"""
    if get_system_platform() == 'android':
        # Media Codec hardware acceleration is mandatory, otherwise only the audio stream is played
        try:
            json_rpc('Settings.SetSettingValue', {'setting': 'videoplayer.usemediacodecsurface', 'value': True})
            json_rpc('Settings.SetSettingValue', {'setting': 'videoplayer.usemediacodec', 'value': True})
        except IOError as exc:
            LOG.error('Changing Kodi settings caused the following error: {}', exc)
