# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2021 Stefano Gottardo - @CastagnaIT (original implementation module)
    Wrappers of Kodi methods and objects

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from typing import Dict, List, Tuple

import xbmc
import xbmcgui

from resources.lib.globals import G

# Convert the deprecated ListItem.setInfo keys to use method names of the new xbmc.InfoTagVideo object
INFO_CONVERT_KEY = {
    'Title': 'setTitle',
    'Year': 'setYear',
    'Plot': 'setPlot',
    'PlotOutline': 'setPlotOutline',
    'Season': 'setSeason',
    'Episode': 'setEpisode',
    'Rating': 'setRating',
    'UserRating': 'setUserRating',
    'Mpaa': 'setMpaa',
    'Duration': 'setDuration',
    'Trailer': 'setTrailer',
    'DateAdded': 'setDateAdded',
    'Director': 'setDirectors',
    'Writer': 'setWriters',
    'Genre': 'setGenres',
    'MediaType': 'setMediaType',
    'TVShowTitle': 'setTvShowTitle',
    'PlayCount': 'setPlaycount'
}

# xbmcgui.ListItem do not support any kind of object serialisation, then transferring directories of ListItem's
# from two python instances (add-on service instance to an add-on client instance) is usually impossible,
# then better simplify the code despite a slight overhead in directory loading.

# pylint: disable=redefined-builtin,invalid-name,no-member
class ListItemW(xbmcgui.ListItem):
    """
    Wrapper for xbmcgui.ListItem to add support for Pickle serialisation and add some helper functions
    ('offscreen' will be True by default)
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
        if G.IS_OLD_KODI_MODULES:
            super().setInfo('video', state['infolabels'])
            for stream_type, quality_info in state['stream_info'].items():
                super().addStreamInfo(stream_type, quality_info)
        else:
            video_info = super().getVideoInfoTag()
            set_video_info_tag(state['infolabels'], video_info)
            if state['stream_info']:
                video_info.addVideoStream(xbmc.VideoStreamDetail(**state['stream_info']['video']))
                video_info.addAudioStream(xbmc.AudioStreamDetail(**state['stream_info']['audio']))
            # From Kodi 20 "ResumeTime" and "TotalTime" must be set with setResumePoint of InfoTagVideo object
            if 'ResumeTime' in state['properties']:
                resume_time = float(state['properties'].pop('ResumeTime', 0))
                total_time = float(state['properties'].pop('TotalTime', 0))
                video_info.setResumePoint(resume_time, total_time)
        super().setProperties(state['properties'])
        super().setArt(state['art'])
        super().addContextMenuItems(state.get('context_menus', []))
        super().select(state.get('is_selected', False))

    # To improve performances we override the xbmcgui.ListItem methods to store values locally (to self.__dict__)
    # without call the base method, then when the object will be unpickled with __setstate__,
    # the local values will be assigned to the base original ListItem methods.

    def setInfo(self, type: str, infoLabels: Dict[str, str]):
        # NOTE: 'type' argument is ignored because we use only 'video' type, but kept for future changes
        if G.IS_SERVICE:
            self.__dict__['infolabels'] = infoLabels
        else:
            super().setInfo(type, infoLabels)

    def getProperty(self, key: str):
        if G.IS_SERVICE:
            return self.__dict__['properties'].get(key)
        return super().getProperty(key)

    def setProperty(self, key: str, value: str):
        if G.IS_SERVICE:
            self.__dict__['properties'][key] = value
        else:
            super().setProperty(key, value)

    def setProperties(self, dictionary: Dict[str, str]):
        if G.IS_SERVICE:
            self.__dict__['properties'].update(dictionary)
        else:
            super().setProperties(dictionary)

    def getArt(self, key: str):
        if G.IS_SERVICE:
            return self.__dict__['art'].get(key)
        return super().getArt(key)

    def setArt(self, dictionary: Dict[str, str]):
        if G.IS_SERVICE:
            self.__dict__['art'].update(dictionary)
        else:
            super().setArt(dictionary)

    def addStreamInfo(self, cType: str, dictionary: Dict[str, str]):
        if G.IS_SERVICE:
            self.__dict__['stream_info'][cType] = dictionary
        else:
            super().addStreamInfo(cType, dictionary)

    def addContextMenuItems(self, items: List[Tuple[str, str]], replaceItems=False):
        if G.IS_SERVICE:
            self.__dict__['context_menus'] = items
        else:
            super().addContextMenuItems(items, replaceItems)

    def isSelected(self):
        if G.IS_SERVICE:
            return self.__dict__.get('is_selected', False)
        return super().isSelected()

    def select(self, selected: bool):
        if G.IS_SERVICE:
            self.__dict__['is_selected'] = selected
        else:
            super().select(selected)

    # Custom helper methods, for service instance only

    def addStreamInfoFromDict(self, dictionary):
        """
        Add or update all stream info from a dictionary
        [CAN BE USED ON SERVICE INSTANCE ONLY]
        """
        self.__dict__['stream_info'].update(dictionary)

    def updateInfo(self, dictionary):
        """
        Add or update data over the existing data previously added with 'setInfo'
        [CAN BE USED ON SERVICE INSTANCE ONLY]
        """
        self.__dict__['infolabels'].update(dictionary)


def set_video_info_tag(info: Dict[str, str], video_info_tag: xbmc.InfoTagVideo):
    """Convert old info data (for ListItem.setInfo) and use it to set the new methods of InfoTagVideo object"""
    # From Kodi v20 ListItem.setInfo is deprecated, we need to use the methods of InfoTagVideo object
    # "Cast" and "Tag" keys need to be converted
    cast_names = info.pop('Cast', [])
    video_info_tag.setCast([xbmc.Actor(name) for name in cast_names])
    tag_names = info.pop('Tag', [])
    video_info_tag.setTagLine(' / '.join(tag_names))
    for key, value in info.items():
        getattr(video_info_tag, INFO_CONVERT_KEY[key])(value)
