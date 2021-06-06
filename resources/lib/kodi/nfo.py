# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2019 Smeulf (original implementation module)
    Functions for Kodi library NFO creation

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import xml.etree.ElementTree as ET
from resources.lib.globals import G
import resources.lib.common as common
import resources.lib.kodi.ui as ui
from resources.lib.utils.logging import LOG


class NFOSettings:
    def __init__(self, enforce=None):
        """
        :param enforce: Used for export new episode, to force the nfo export status
        """
        if enforce is None:
            self._enabled = G.ADDON.getSettingBool('enable_nfo_export')
            self._export_tvshow_id = G.ADDON.getSettingInt('export_tvshow_nfo')
        else:
            LOG.debug('Export NFO enforced to {}', enforce)
            self._enabled = enforce
            self._export_tvshow_id = enforce

        self._export_movie_id = G.ADDON.getSettingInt('export_movie_nfo')
        self._export_full_tvshow = G.ADDON.getSettingBool('export_full_tvshow_nfo')

    @property
    def export_enabled(self):
        """Return True if NFO Export is enabled"""
        return self._enabled

    @property
    def export_movie_enabled(self):
        """Return True if Movie NFO Export is enabled (also depends on the export dialog)"""
        return self._enabled and self._export_movie_id != 0

    @property
    def export_tvshow_enabled(self):
        """Return True if TvShow NFO Export is enabled (also depends on the export dialog)"""
        return self._enabled and self._export_tvshow_id != 0

    @property
    def export_full_tvshow(self):
        """Return True if full NFO must be exported (also depends on the export dialog)
         i.e. create tvshow.nfo
         The file tvshow.nfo should be exported only when 'Local Information' scraper is used,
         if it is exported while using other scrapers (like TMDB),
         they will not get the full information for the tv show from the internet database"""
        return self._enabled and self._export_full_tvshow and self.export_tvshow_enabled

    @property
    def movie_prompt_dialog(self):
        """Ask to user when export Movie NFO"""
        return self._enabled and self._export_movie_id == 2

    @property
    def tvshow_prompt_dialog(self):
        """Ask to user when export TvShow NFO"""
        return self._enabled and self._export_tvshow_id == 2

    def show_export_dialog(self, mediatype=None):
        """Ask the user if he wants to export NFO for movies and/or tvshows, this override the default settings"""
        if not self.export_enabled or (not self.movie_prompt_dialog and not self.tvshow_prompt_dialog):
            return
        ask_message_typelist = []
        if mediatype == common.VideoId.MOVIE and self.movie_prompt_dialog:
            ask_message_typelist.append(common.get_local_string(30189))
        if mediatype in common.VideoId.TV_TYPES and self.tvshow_prompt_dialog:
            ask_message_typelist.append(common.get_local_string(30190))
        if not mediatype:
            # If 'None' a massive export has been requested (i.e. first library sync, manual sync, my list auto-sync...)
            if self.movie_prompt_dialog:
                ask_message_typelist.append(common.get_local_string(30189))
            if self.tvshow_prompt_dialog:
                ask_message_typelist.append(common.get_local_string(30190))
        if ask_message_typelist:
            message = f' {common.get_local_string(1397)} '.join(ask_message_typelist)
            message = common.get_local_string(30183).format(message) + common.get_local_string(30192)
            user_choice = ui.ask_for_confirmation(common.get_local_string(30182), message)
            if len(ask_message_typelist) == 2 and not user_choice:
                self._export_movie_id = 0
                self._export_tvshow_id = 0
            elif common.get_local_string(30189) in ask_message_typelist and not user_choice:
                self._export_movie_id = 0
            elif common.get_local_string(30190) in ask_message_typelist and not user_choice:
                self._export_tvshow_id = 0


def create_episode_nfo(episode, season, show):
    """Build NFO file for episode"""
    tags = {
        'title': episode.get('title'),
        'showtitle': show.get('title'),
        'season': season.get('seq'),
        'episode': episode.get('seq'),
        'plot': episode.get('synopsis'),
        'runtime': episode.get('runtime', 0) / 60,
        'year': season.get('year'),
        'id': episode.get('id')
    }

    root = _build_root_node('episodedetails', tags)
    _add_episode_thumb(root, episode)
    return root


def create_show_nfo(show):
    """Build NFO file for TV Show"""
    tags = {
        'title': show['title'],
        'showtitle': show['title'],
        'plot': show.get('synopsis'),
        'id': show['id'],
        'mpaa': show.get('rating')
    }
    root = _build_root_node('tvshow', tags)
    _add_poster(root, show)
    _add_fanart(root, show)
    return root


def create_movie_nfo(movie):
    tags = {
        'title': movie.get('title'),
        'plot': movie.get('synopsis'),
        'id': movie.get('id'),
        'mpaa': movie.get('rating'),
        'year': movie.get('year'),
        'runtime': movie.get('runtime', 0) / 60,
    }
    root = _build_root_node('movie', tags)
    _add_poster(root, movie)
    _add_fanart(root, movie)
    return root


def _add_episode_thumb(root, episode):
    if episode.get('thumbs'):
        for thumb in episode['thumbs']:
            url = thumb['url']
            thumbnail = ET.SubElement(root, 'thumb')
            thumbnail.text = url


def _add_poster(root, data):
    if data.get('boxart'):
        for boxart in data['boxart']:
            url = boxart['url']
            poster = ET.SubElement(root, 'thumb', {'aspect': 'poster'})
            poster.text = url


def _add_fanart(root, data):
    if data.get('storyart'):
        for storyart in data['storyart']:
            url = storyart['url']
            fanart = ET.SubElement(root, 'fanart')
            thumb = ET.SubElement(fanart, 'thumb')
            thumb.text = url


def _build_root_node(root_name, tags):
    root = ET.Element(root_name)
    for (k, v) in list(tags.items()):
        if v:
            tag = ET.SubElement(root, k)
            tag.text = str(v)
    return root
