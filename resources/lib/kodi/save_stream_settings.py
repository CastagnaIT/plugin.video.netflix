# pylint: disable=invalid-name,missing-docstring
# pylint: disable=attribute-defined-outside-init,import-error
from platform import machine

import xbmcgui


ACTION_PLAYER_STOP = 13
OS_MACHINE = machine()


class SaveStreamSettings(xbmcgui.WindowXMLDialog):
    """
    Dialog for skipping video parts (intro, recap, ...)
    """
    def __init__(self, *args, **kwargs):
        self.stream_settings = kwargs['stream_settings']
        self.tvshowid = kwargs['tvshowid']
        self.storage = kwargs['storage']
        if OS_MACHINE[0:5] == 'armv7':
            xbmcgui.WindowXMLDialog.__init__(self)
        else:
            xbmcgui.WindowXMLDialog.__init__(self, *args, **kwargs)

    def onInit(self):
        self.action_exitkeys_id = [10, 13]

    def onClick(self, controlID):
        if controlID == 6012:
            self.storage[self.tvshowid] = self.stream_settings
            self.close()
