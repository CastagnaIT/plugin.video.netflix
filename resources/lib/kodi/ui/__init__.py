# -*- coding: utf-8 -*-

"""Kodi GUI stuff"""
from __future__ import unicode_literals

import xbmc

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
