# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    XML based dialogs

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import time

import xbmc
import xbmcgui

from resources.lib.common import run_threaded, make_call
from resources.lib.globals import G


ACTION_PREVIOUS_MENU = 10
ACTION_PLAYER_STOP = 13
ACTION_NAV_BACK = 92
ACTION_NOOP = 999

CMD_CLOSE_DIALOG_BY_NOOP = 'AlarmClock(closedialog,Action(noop),{},silent)'


# @time_execution(immediate=True)
def show_modal_dialog(non_blocking, dlg_class, xml_filename, **kwargs):
    """
    Show a modal Dialog in the UI.
    Pass kwargs minutes and/or seconds to have the dialog automatically
    close after the specified time.

    :return if exists return self.return_value value of dlg_class (if non_blocking=True return always None)
    """
    # WARNING: doModal when invoked does not release the function immediately!
    # it seems that doModal waiting for all window operations to be completed before return,
    # for example the "Skip" dialog takes about 30 seconds to release the function (probably for the included animation)
    # To be taken into account because it can do very big delays in the execution of the invoking code
    return run_threaded(non_blocking, _show_modal_dialog, dlg_class, xml_filename, **kwargs)


def _show_modal_dialog(dlg_class, xml_filename, **kwargs):
    dlg = dlg_class(xml_filename, G.ADDON.getAddonInfo('path'), 'default', '1080i', **kwargs)
    minutes = kwargs.get('minutes', 0)
    seconds = kwargs.get('seconds', 0)
    if minutes > 0 or seconds > 0:
        # Bug in Kodi AlarmClock function, if only the seconds are passed
        # the time conversion inside the function multiply the seconds by 60
        if seconds > 59 and minutes == 0:
            alarm_time = time.strftime('%M:%S', time.gmtime(seconds))
        else:
            alarm_time = f'{minutes:02d}:{seconds:02d}'
        xbmc.executebuiltin(CMD_CLOSE_DIALOG_BY_NOOP.format(alarm_time))
    dlg.doModal()
    if hasattr(dlg, 'return_value'):
        return dlg.return_value
    return None


# pylint: disable=invalid-name
class Skip(xbmcgui.WindowXMLDialog):
    """Dialog for skipping video parts (intro, recap, ...)"""

    def __init__(self, *args, **kwargs):
        self.seek_time = kwargs['seek_time']
        self.label = kwargs['label']
        self.action_exit_keys_id = [ACTION_PREVIOUS_MENU,
                                    ACTION_PLAYER_STOP,
                                    ACTION_NAV_BACK,
                                    ACTION_NOOP]
        super().__init__(*args)

    def onInit(self):
        self.getControl(6012).setLabel(self.label)  # pylint: disable=no-member

    def onClick(self, controlId):
        if controlId == 6012:
            xbmc.Player().seekTime(self.seek_time)
            self.close()

    def onAction(self, action):
        if action.getId() in self.action_exit_keys_id:
            self.close()


def show_skip_dialog(dialog_duration, seek_time, label):
    """Show a dialog for ESN and Widevine settings"""
    show_modal_dialog(True,
                      Skip,
                      "plugin-video-netflix-Skip.xml",
                      seconds=dialog_duration,
                      seek_time=seek_time,
                      label=label)


def show_parental_dialog(**kwargs):
    """Show a dialog for parental control settings"""
    from resources.lib.kodi.ui.xmldialog_parental import ParentalControl
    show_modal_dialog(False,
                      ParentalControl,
                      'plugin-video-netflix-ParentalControl.xml',
                      **kwargs)


def show_rating_thumb_dialog(**kwargs):
    """Show a dialog for rating with thumb"""
    from resources.lib.kodi.ui.xmldialog_ratingthumb import RatingThumb
    show_modal_dialog(False,
                      RatingThumb,
                      'plugin-video-netflix-RatingThumb.xml',
                      **kwargs)


def show_profiles_dialog(title=None, title_prefix=None, preselect_guid=None):
    """
    Show a dialog to select a profile
    :return guid of selected profile or None
    """
    if not title:
        title = G.ADDON.getLocalizedString(30128)
    if title_prefix:
        title = f'{title_prefix} - {title}'
    # Get profiles data
    # pylint: disable=unused-variable
    dir_items, extra_data = make_call('get_profiles',
                                      {'request_update': True,
                                       'preselect_guid': preselect_guid,
                                       'detailed_info': False})
    from resources.lib.kodi.ui.xmldialog_profiles import Profiles
    return show_modal_dialog(False,
                             Profiles,
                             'plugin-video-netflix-Profiles.xml',
                             title=title,
                             dir_items=dir_items,
                             preselect_guid=preselect_guid)


def show_esn_widevine_dialog():
    """Show a dialog for ESN and Widevine settings"""
    from resources.lib.kodi.ui.xmldialog_esnwidevine import ESNWidevine
    return show_modal_dialog(False,
                             ESNWidevine,
                             'plugin-video-netflix-ESN-Widevine.xml')
