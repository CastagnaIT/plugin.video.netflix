# -*- coding: utf-8 -*-
# pylint: disable=invalid-name,missing-docstring,attribute-defined-outside-init
"""XML based dialogs"""
from __future__ import unicode_literals

from platform import machine

import xbmc
import xbmcgui

ACTION_PLAYER_STOP = 13
OS_MACHINE = machine()

CMD_AUTOCLOSE_DIALOG = 'AlarmClock(closedialog,Dialog.Close(all,true),' \
                       '{:02d}:{:02d},silent)'


def show_modal_dialog(dlg_class, xml, path, **kwargs):
    """
    Show a modal Dialog in the UI.
    Pass kwargs minutes and/or seconds tohave the dialog automatically
    close after the specified time.
    """
    dlg = dlg_class(xml, path, 'default', '1080i', **kwargs)
    minutes = kwargs.get('minutes', 0)
    seconds = kwargs.get('seconds', 0)
    if minutes > 0 or seconds > 0:
        xbmc.executebuiltin(CMD_AUTOCLOSE_DIALOG.format(minutes, seconds))
    dlg.doModal()


class Skip(xbmcgui.WindowXMLDialog):
    """
    Dialog for skipping video parts (intro, recap, ...)
    """
    def __init__(self, *args, **kwargs):
        self.skip_to = kwargs['skip_to']
        self.label = kwargs['label']
        if OS_MACHINE[0:5] == 'armv7':
            xbmcgui.WindowXMLDialog.__init__(self)
        else:
            xbmcgui.WindowXMLDialog.__init__(self, *args, **kwargs)

    def onInit(self):
        self.action_exitkeys_id = [10, 13]
        self.getControl(6012).setLabel(self.label)

    def onClick(self, controlID):
        if controlID == 6012:
            xbmc.Player().seekTime(self.skip_to)
            self.close()


class SaveStreamSettings(xbmcgui.WindowXMLDialog):
    """
    Dialog for skipping video parts (intro, recap, ...)
    """
    def __init__(self, *args, **kwargs):
        super(SaveStreamSettings, self).__init__(*args, **kwargs)
        self.new_show_settings = kwargs['new_show_settings']
        self.tvshowid = kwargs['tvshowid']
        self.storage = kwargs['storage']

    def onInit(self):
        self.action_exitkeys_id = [10, 13]

    def onClick(self, controlID):
        if controlID == 6012:
            self.storage[self.tvshowid] = self.new_show_settings
            self.close()
