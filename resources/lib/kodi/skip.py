# pylint: disable=invalid-name,missing-docstring,attribute-defined-outside-init,
# pylint: disable=import-error
from platform import machine

import xbmc
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
            xbmc.Player().seekTime(self.skip_to)
            self.close()
