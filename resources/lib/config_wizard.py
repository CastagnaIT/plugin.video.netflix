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

from resources.lib.common.exceptions import InputStreamHelperError
from resources.lib.common import get_system_platform, is_device_4k_capable, get_local_string, json_rpc
from resources.lib.globals import G
from resources.lib.kodi.ui import show_ok_dialog
from resources.lib.utils.logging import LOG


def run_addon_configuration(show_end_msg=False):
    """
    Add-on configuration wizard,
    automatically configures profiles and add-ons dependencies, based on user-supplied data and device characteristics
    """
    system = get_system_platform()
    LOG.debug('Running add-on configuration wizard ({})', system)
    is_4k_capable = is_device_4k_capable()

    _set_profiles(system, is_4k_capable)
    _set_kodi_settings(system)
    _set_isa_addon_settings(is_4k_capable, system == 'android')

    # This settings for now used only with android devices and it should remain disabled (keep it for test),
    # in the future it may be useful for other platforms or it may be removed
    G.ADDON.setSettingBool('enable_force_hdcp', False)

    # Enable UpNext if it is installed and enabled
    G.ADDON.setSettingBool('UpNextNotifier_enabled', getCondVisibility('System.AddonIsEnabled(service.upnext)'))
    if show_end_msg:
        show_ok_dialog(get_local_string(30154), get_local_string(30157))


def _set_isa_addon_settings(is_4k_capable, hdcp_override):
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

    isa_addon = Addon('inputstream.adaptive')
    isa_addon.setSettingBool('HDCPOVERRIDE', hdcp_override)
    if isa_addon.getSettingInt('STREAMSELECTION') == 1:
        # Stream selection must never be set to 'Manual' or cause problems with the streams
        isa_addon.setSettingInt('STREAMSELECTION', 0)
    # 'Ignore display' should only be set when Kodi display resolution is not 4K
    isa_addon.setSettingBool('IGNOREDISPLAY', is_4k_capable and (getScreenWidth() != 3840 or getScreenHeight() != 2160))


def _set_profiles(system, is_4k_capable):
    """Method for self-configuring of netflix manifest profiles"""
    enable_vp9_profiles = True
    enable_hevc_profiles = False
    if system == 'android':
        # By default we do not enable VP9 because on some devices do not fully support it
        enable_vp9_profiles = False
        # By default we do not enable HEVC because not all device support it, then enable it only on 4K capable devices
        enable_hevc_profiles = is_4k_capable
    G.ADDON.setSettingBool('enable_vp9_profiles', enable_vp9_profiles)
    G.ADDON.setSettingBool('enable_hevc_profiles', enable_hevc_profiles)

    # Todo: currently lacks a method on Kodi to know if HDR is supported and currently enabled
    #       as soon as the method is available it will be possible to automate all HDR code selection
    #       and remove the HDR settings (already present in Kodi settings)
    # if is_4k_capable and ***kodi_hdr_enabled***:
    #     _ask_dolby_vision()


def _ask_dolby_vision():
    # Todo: ask to user if want to enable dolby vision
    pass


def _set_kodi_settings(system):
    """Method for self-configuring Kodi settings"""
    if system == 'android':
        # Media Codec hardware acceleration is mandatory, otherwise only the audio stream is played
        try:
            json_rpc('Settings.SetSettingValue', {'setting': 'videoplayer.usemediacodecsurface', 'value': True})
            json_rpc('Settings.SetSettingValue', {'setting': 'videoplayer.usemediacodec', 'value': True})
        except IOError as exc:
            LOG.error('Changing Kodi settings caused the following error: {}', exc)
