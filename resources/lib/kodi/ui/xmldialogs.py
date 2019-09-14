# -*- coding: utf-8 -*-
# pylint: disable=invalid-name,missing-docstring,attribute-defined-outside-init
"""XML based dialogs"""
from __future__ import absolute_import, division, unicode_literals

import time
from platform import machine

import xbmc
import xbmcgui

ACTION_PREVIOUS_MENU = 10
ACTION_PLAYER_STOP = 13
ACTION_NAV_BACK = 92
ACTION_NOOP = 999

OS_MACHINE = machine()

CMD_CLOSE_DIALOG_BY_NOOP = 'AlarmClock(closedialog,Action(noop),{},silent)'


def show_modal_dialog(dlg_class, xml, path, **kwargs):
    """
    Show a modal Dialog in the UI.
    Pass kwargs minutes and/or seconds to have the dialog automatically
    close after the specified time.
    """
    dlg = dlg_class(xml, path, 'default', '1080i', **kwargs)
    minutes = kwargs.get('minutes', 0)
    seconds = kwargs.get('seconds', 0)
    if minutes > 0 or seconds > 0:
        # Bug in Kodi AlarmClock function, if only the seconds are passed
        # the time conversion inside the function multiply the seconds by 60
        if seconds > 59 and minutes == 0:
            alarm_time = time.strftime('%M:%S', time.gmtime(seconds))
        else:
            alarm_time = '{:02d}:{:02d}'.format(minutes, seconds)
        xbmc.executebuiltin(CMD_CLOSE_DIALOG_BY_NOOP.format(alarm_time))
    dlg.doModal()


class Skip(xbmcgui.WindowXMLDialog):
    """
    Dialog for skipping video parts (intro, recap, ...)
    """
    def __init__(self, *args, **kwargs):
        self.skip_to = kwargs['skip_to']
        self.label = kwargs['label']

        self.action_exitkeys_id = [ACTION_PREVIOUS_MENU,
                                   ACTION_PLAYER_STOP,
                                   ACTION_NAV_BACK,
                                   ACTION_NOOP]

        if OS_MACHINE[0:5] == 'armv7':
            xbmcgui.WindowXMLDialog.__init__(self)
        else:
            xbmcgui.WindowXMLDialog.__init__(self, *args, **kwargs)

    def onInit(self):
        self.getControl(6012).setLabel(self.label)

    def onClick(self, controlID):
        if controlID == 6012:
            xbmc.Player().seekTime(self.skip_to)
            self.close()

    def onAction(self, action):
        if action.getId() in self.action_exitkeys_id:
            self.close()
