# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2021 Stefano Gottardo - @CastagnaIT (original implementation module)
    Wrappers of Kodi methods and objects

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from typing import Dict, List, Tuple

import xbmcgui


# pylint: disable=redefined-builtin,invalid-name
class ListItemW(xbmcgui.ListItem):
    """
    Wrapper for xbmcgui.ListItem
    to make it serializable with Pickle and provide helper functions ('offscreen' will be True by default)
    """

    def __init__(self, label='', label2='', path=''):
        super().__init__(label, label2, path, True)
        self.__dict__.update({
            'properties': {},
            'infolabels': {},
            'art': {},
            'stream_info': {}
        })

    def __getnewargs__(self):  # Pickle method
        """Passes arguments to __new__ method"""
        return self.getLabel(), self.getLabel2(), self.getPath(), True

    def __setstate__(self, state):  # Pickle method
        """Restore the state of the object data"""
        self.setContentLookup(False)
        super().setInfo('video', state['infolabels'])
        super().setProperties(state['properties'])
        super().setArt(state['art'])
        for stream_type, quality_info in state['stream_info'].items():
            super().addStreamInfo(stream_type, quality_info)
        super().addContextMenuItems(state.get('context_menus', []))
        super().select(state.get('is_selected', False))

    # In the 'xbmcgui.ListItem' is missing a lot of get/set methods then pickle cannot be implemented on C++ side,
    #   so we override these methods to store locally the values that will be re-assigned when the object
    #   will be unpickled with __setstate__, if is needed reuse these methods remove the comments from the code,
    #   the data assignment to the original ListItem object is initially avoided to improve performance

    def setInfo(self, type: str, infoLabels: Dict[str, str]):
        # NOTE: 'type' argument is ignored because we use only 'video' type, but kept for future changes
        # super().setInfo(type, infoLabels)
        self.__dict__['infolabels'] = infoLabels

    def setProperty(self, key: str, value: str):
        super().setProperty(key, value)
        self.__dict__['properties'][key] = value

    def setProperties(self, dictionary: Dict[str, str]):
        super().setProperties(dictionary)
        self.__dict__['properties'].update(dictionary)

    def setArt(self, dictionary: Dict[str, str]):
        # super().setArt(dictionary)
        self.__dict__['art'].update(dictionary)

    def addStreamInfo(self, cType: str, dictionary: Dict[str, str]):
        # super().addStreamInfo(cType, dictionary)
        self.__dict__['stream_info'][cType] = dictionary

    def addContextMenuItems(self, items: List[Tuple[str, str]], replaceItems=False):
        # NOTE: 'replaceItems' argument is ignored because not works
        # super().addContextMenuItems(items)
        self.__dict__['context_menus'] = items

    def select(self, selected: bool):
        # super().select(selected)
        self.__dict__['is_selected'] = selected

    # Custom helper methods

    def addStreamInfoFromDict(self, dictionary):
        """Add or update all stream info from a dictionary"""
        self.__dict__['stream_info'].update(dictionary)

    def updateInfo(self, dictionary):
        """Add or update data over the existing data previously added with 'setInfo'"""
        self.__dict__['infolabels'].update(dictionary)
