# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2020 Stefano Gottardo - @CastagnaIT (original implementation module)
    Miscellaneous utility functions related to the device

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals
import xbmc

from resources.lib.globals import G
from resources.lib.utils.esn import ForceWidevine
from resources.lib.utils.logging import LOG


def select_port(service):
    """Select an unused port on the host machine for a server and store it in the settings"""
    port = select_unused_port()
    G.LOCAL_DB.set_value('{}_service_port'.format(service.lower()), port)
    LOG.info('[{}] Picked Port: {}'.format(service, port))
    return port


def select_unused_port():
    """
    Helper function to select an unused port on the host machine

    :return: int - Free port
    """
    import socket
    from contextlib import closing
    # pylint: disable=no-member
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(('127.0.0.1', 0))
        _, port = sock.getsockname()
        return port


def get_system_platform():
    if not hasattr(get_system_platform, 'cached'):
        platform = "unknown"
        if xbmc.getCondVisibility('system.platform.linux') and not xbmc.getCondVisibility('system.platform.android'):
            if xbmc.getCondVisibility('system.platform.linux.raspberrypi'):
                platform = "linux raspberrypi"
            else:
                platform = "linux"
        elif xbmc.getCondVisibility('system.platform.linux') and xbmc.getCondVisibility('system.platform.android'):
            platform = "android"
        elif xbmc.getCondVisibility('system.platform.uwp'):
            platform = "uwp"
        elif xbmc.getCondVisibility('system.platform.windows'):
            platform = "windows"
        elif xbmc.getCondVisibility('system.platform.osx'):
            platform = "osx"
        elif xbmc.getCondVisibility('system.platform.ios'):
            platform = "ios"
        elif xbmc.getCondVisibility('system.platform.tvos'):  # Supported only on Kodi 19.x
            platform = "tvos"
        get_system_platform.cached = platform
    return get_system_platform.cached


def get_machine():
    """Get machine architecture"""
    from platform import machine
    try:
        return machine()
    except Exception:  # pylint: disable=broad-except
        # Due to OS restrictions on 'ios' and 'tvos' this generate an exception
        # See python limits in the wiki development page
        # Fallback with a generic arm
        return 'arm'


def is_device_4k_capable():
    """Check if the device is 4k capable"""
    # Currently only on android is it possible to use 4K
    if get_system_platform() == 'android':
        from resources.lib.database.db_utils import TABLE_SESSION
        # Check if the drm has security level L1
        is_l3_forced = G.ADDON.getSettingString('force_widevine') != ForceWidevine.DISABLED
        is_drm_l1_security_level = (G.LOCAL_DB.get_value('drm_security_level', '', table=TABLE_SESSION) == 'L1'
                                    and not is_l3_forced)
        # Check if HDCP level is 2.2 or up
        hdcp_level = get_hdcp_level()
        hdcp_4k_capable = hdcp_level and hdcp_level >= 2.2
        return bool(is_drm_l1_security_level and hdcp_4k_capable)
    return False


def get_hdcp_level():
    """Get the HDCP level when exist else None"""
    from re import findall
    from resources.lib.database.db_utils import TABLE_SESSION
    drm_hdcp_level = findall('\\d+\\.\\d+', G.LOCAL_DB.get_value('drm_hdcp_level', '', table=TABLE_SESSION))
    return float(drm_hdcp_level[0]) if drm_hdcp_level else None


def get_user_agent(enable_android_mediaflag_fix=False):
    """
    Determines the user agent string for the current platform.
    Needed to retrieve a valid ESN (except for Android, where the ESN can be generated locally)

    :returns: str -- User agent string
    """
    system = get_system_platform()
    if enable_android_mediaflag_fix and system == 'android' and is_device_4k_capable():
        # The UA affects not only the ESNs in the login, but also the video details,
        # so the UAs seem refer to exactly to these conditions: https://help.netflix.com/en/node/23742
        # This workaround is needed because currently we do not login through the netflix native android API,
        # but redirect everything through the website APIs, and the website APIs do not really support android.
        # Then on android usually we use the 'arm' UA which refers to chrome os, but this is limited to 1080P, so the
        # labels on the 4K devices appears wrong (in the Kodi skin the 4K videos have 1080P media flags instead of 4K),
        # the Windows UA is not limited, so we can use it to get the right video media flags.
        system = 'windows'

    chrome_version = 'Chrome/84.0.4147.136'
    base = 'Mozilla/5.0 '
    base += '%PL% '
    base += 'AppleWebKit/537.36 (KHTML, like Gecko) '
    base += '%CH_VER% Safari/537.36'.replace('%CH_VER%', chrome_version)

    if system in ['osx', 'ios', 'tvos']:
        return base.replace('%PL%', '(Macintosh; Intel Mac OS X 10_15_5)')
    if system in ['windows', 'uwp']:
        return base.replace('%PL%', '(Windows NT 10.0; Win64; x64)')
    # ARM based Linux
    if get_machine().startswith('arm'):
        # Last number is the platform version of Chrome OS
        return base.replace('%PL%', '(X11; CrOS armv7l 13099.110.0)')
    # x86 Linux
    return base.replace('%PL%', '(X11; Linux x86_64)')


def is_internet_connected():
    """
    Check internet status
    :return: True if connected
    """
    if not xbmc.getCondVisibility('System.InternetState'):
        # Double check when Kodi say that it is not connected
        # i'm not sure the InfoLabel will work properly when Kodi was started a few seconds ago
        # using getInfoLabel instead of getCondVisibility often return delayed results..
        return _check_internet()
    return True


def _check_internet():
    """
    Checks via socket if the internet works (in about 0,7sec with no timeout error)
    :return: True if connected
    """
    import socket
    for timeout in [1, 1]:
        try:
            socket.setdefaulttimeout(timeout)
            host = socket.gethostbyname("www.google.com")
            s = socket.create_connection((host, 80), timeout)
            s.close()
            return True
        except Exception:  # pylint: disable=broad-except
            # Error when is not reachable
            pass
    return False
