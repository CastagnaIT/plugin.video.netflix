# pylint: disable=invalid-name,missing-docstring
# pylint: disable=attribute-defined-outside-init,import-error
from platform import machine

import xbmcgui

ACTION_PLAYER_STOP = 13
OS_MACHINE = machine()


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
            import xbmc
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
