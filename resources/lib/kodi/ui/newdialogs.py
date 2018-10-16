# -*- coding: utf-8 -*-
# pylint: disable=unused-import
"""Simple and statically defined dialogs"""
from __future__ import unicode_literals

import xbmcgui

def show_password_dialog():
    """
    Asks the user for its Netflix password

    :returns: str - Netflix password
    """
    from resources.lib.common import ADDON
    return xbmcgui.Dialog().input(
        heading=ADDON.getLocalizedString(30004),
        type=xbmcgui.INPUT_ALPHANUM,
        option=xbmcgui.ALPHANUM_HIDE_INPUT)

def show_email_dialog():
    """
    Asks the user for its Netflix account email

    :returns: str - Netflix account email
    """
    from resources.lib.common import ADDON
    return xbmcgui.Dialog().input(
        heading=ADDON.getLocalizedString(30005),
        type=xbmcgui.INPUT_ALPHANUM)
