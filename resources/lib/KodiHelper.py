# pylint: skip-file
# -*- coding: utf-8 -*-
# Module: KodiHelper
# Created on: 13.01.2017

import re
import json
import base64
import hashlib
from os import remove
from uuid import uuid4
from urllib import urlencode
import AddonSignals
import xbmc
import xbmcgui
import xbmcplugin
import inputstreamhelper
from resources.lib.ui.Dialogs import Dialogs
from resources.lib.NetflixCommon import Signals
from utils import get_user_agent
from UniversalAnalytics import Tracker
try:
    import cPickle as pickle
except:
    import pickle
try:
    # Python 2.6-2.7
    from HTMLParser import HTMLParser
except ImportError:
    # Python 3
    from html.parser import HTMLParser

VIEW_FOLDER = 'folder'
VIEW_MOVIE = 'movie'
VIEW_SHOW = 'show'
VIEW_SEASON = 'season'
VIEW_EPISODE = 'episode'
VIEW_EXPORTED = 'exported'

CONTENT_FOLDER = 'files'
CONTENT_MOVIE = 'movies'
CONTENT_SHOW = 'tvshows'
CONTENT_SEASON = 'seasons'
CONTENT_EPISODE = 'episodes'


def _update_if_present(source_dict, source_att, target_dict, target_att):
    if source_dict.get(source_att):
        target_dict.update({target_att: source_dict[source_att]})


class KodiHelper(object):
    """
    Consumes all the configuration data from Kodi as well as
    turns data into lists of folders and videos"""

    def __init__(self, nx_common, library):
        """
        Provides helpers for addon side (not service side)
        """
        self.nx_common = nx_common
        self.plugin_handle = nx_common.plugin_handle
        self.base_url = nx_common.base_url
        self.library = library
        self.custom_export_name = nx_common.get_setting('customexportname')
        self.show_update_db = nx_common.get_setting('show_update_db')
        self.default_fanart = nx_common.get_addon_info('fanart')
        self.setup_memcache()
        self.dialogs = Dialogs(
            get_local_string=self.get_local_string,
            custom_export_name=self.custom_export_name)
        self._context_menu_actions = None

    def refresh(self):
        """Refresh the current list"""
        return xbmc.executebuiltin('Container.Refresh')

    def toggle_adult_pin(self):
        """Toggles the adult pin setting"""
        adultpin_enabled = False
        raw_adultpin_enabled = self.nx_common.get_setting('adultpin_enable')
        if raw_adultpin_enabled == 'true' or raw_adultpin_enabled == 'True':
            adultpin_enabled = True
        if adultpin_enabled is False:
            return self.nx_common.set_setting('adultpin_enable', 'True')
        return self.nx_common.set_setting('adultpin_enable', 'False')

    def set_main_menu_selection(self, type):
        """Persist the chosen main menu entry in memory

        Parameters
        ----------
        type : :obj:`str`
            Selected menu item
        """
        current_window = xbmcgui.getCurrentWindowId()
        xbmcgui.Window(current_window).setProperty('main_menu_selection', type)

    def get_main_menu_selection(self):
        """Gets the persisted chosen main menu entry from memory

        Returns
        -------
        :obj:`str`
            The last chosen main menu entry
        """
        current_window = xbmcgui.getCurrentWindowId()
        window = xbmcgui.Window(current_window)
        return window.getProperty('main_menu_selection')

    def setup_memcache(self):
        """Sets up the memory cache if not existant"""
        current_window = xbmcgui.getCurrentWindowId()
        window = xbmcgui.Window(current_window)
        try:
            cached_items = window.getProperty('memcache')
            # no cache setup yet, create one
            if len(cached_items) < 1:
                window.setProperty('memcache', pickle.dumps({}))
        except EOFError:
            pass

    def invalidate_memcache(self):
        """Invalidates the memory cache"""
        current_window = xbmcgui.getCurrentWindowId()
        window = xbmcgui.Window(current_window)
        try:
            window.setProperty('memcache', pickle.dumps({}))
        except EOFError:
            pass

    def get_cached_item(self, cache_id):
        """Returns an item from the in memory cache

        Parameters
        ----------
        cache_id : :obj:`str`
            ID of the cache entry

        Returns
        -------
        mixed
            Contents of the requested cache item or none
        """
        ret = None
        current_window = xbmcgui.getCurrentWindowId()
        window = xbmcgui.Window(current_window)
        try:
            cached_items = pickle.loads(window.getProperty('memcache'))
            ret = cached_items.get(cache_id)
        except EOFError:
            ret = None
        return ret

    def add_cached_item(self, cache_id, contents):
        """Adds an item to the in memory cache

        Parameters
        ----------
        cache_id : :obj:`str`
            ID of the cache entry

        contents : mixed
            Cache entry contents
        """
        current_window = xbmcgui.getCurrentWindowId()
        window = xbmcgui.Window(current_window)
        try:
            cached_items = pickle.loads(window.getProperty('memcache'))
            cached_items.update({cache_id: contents})
            window.setProperty('memcache', pickle.dumps(cached_items))
        except EOFError:
            pass

    def set_custom_view(self, content):
        """Set the view mode

        Parameters
        ----------
        content : :obj:`str`

            Type of content in container
            (folder, movie, show, season, episode, login, exported)

        """
        custom_view = self.nx_common.get_setting('customview')
        if custom_view == 'true':
            view = int(self.nx_common.get_setting('viewmode' + content))
            if view != -1:
                xbmc.executebuiltin('Container.SetViewMode(%s)' % view)

    def save_autologin_data(self, autologin_user, autologin_id):
        """Write autologin data to settings

        Parameters
        ----------
        autologin_user : :obj:`str`
            Profile name from netflix

        autologin_id : :obj:`str`
            Profile id from netflix
        """
        self.nx_common.set_setting('autologin_user', autologin_user)
        self.nx_common.set_setting('autologin_id', autologin_id)
        self.nx_common.set_setting('autologin_enable', 'True')
        self.dialogs.show_autologin_enabled_notify()
        self.invalidate_memcache()
        self.refresh()

    def build_profiles_listing(self, profiles, action, build_url):
        """
        Builds the profiles list Kodi screen

        :param profiles: list of user profiles
        :type profiles: list
        :param action: action paramter to build the subsequent routes
        :type action: str
        :param build_url: function to build the subsequent routes
        :type build_url: fn
        :returns: bool -- List could be build
        """
        # init html parser for entity decoding
        html_parser = HTMLParser()
        # build menu items for every profile
        for profile in profiles:
            # load & encode profile data
            enc_profile_name = profile.get('profileName', '').encode('utf-8')
            unescaped_profile_name = html_parser.unescape(enc_profile_name)
            profile_guid = profile.get('guid')

            # build urls
            url = build_url({'action': action, 'profile_id': profile_guid})
            autologin_url = build_url({
                'action': 'save_autologin',
                'autologin_id': profile_guid,
                'autologin_user': enc_profile_name})

            # add list item
            list_item = xbmcgui.ListItem(
                label=unescaped_profile_name,
                iconImage=profile.get('avatar'))
            list_item.setProperty(
                key='fanart_image',
                value=self.default_fanart)
            # add context menu options
            auto_login = (
                self.get_local_string(30053),
                'RunPlugin(' + autologin_url + ')')
            list_item.addContextMenuItems(items=[auto_login])

            # add directory & sorting options
            xbmcplugin.addDirectoryItem(
                handle=self.plugin_handle,
                url=url,
                listitem=list_item,
                isFolder=True)
            xbmcplugin.addSortMethod(
                handle=self.plugin_handle,
                sortMethod=xbmcplugin.SORT_METHOD_LABEL)

        xbmcplugin.setContent(
            handle=self.plugin_handle,
            content=CONTENT_FOLDER)

        return xbmcplugin.endOfDirectory(handle=self.plugin_handle)

    def build_main_menu_listing(self, video_list_ids, user_list_order, actions,
                                build_url, widget_display=False):
        """
        Builds the video lists (my list, continue watching, etc.) Kodi screen

        Parameters
        ----------
        video_list_ids : :obj:`dict` of :obj:`str`
            List of video lists

        user_list_order : :obj:`list` of :obj:`str`
            Ordered user lists
            to determine what should be displayed in the main menue

        actions : :obj:`dict` of :obj:`str`
            Dictionary of actions to build subsequent routes

        build_url : :obj:`fn`
            Function to build the subsequent routes

        Returns
        -------
        bool
            List could be build
        """
        preselect_items = []
        for category in user_list_order:
            for video_list_id in video_list_ids['user']:
                if video_list_ids['user'][video_list_id]['name'] == category:
                    label = video_list_ids['user'][video_list_id]['displayName']
                    if category == 'netflixOriginals':
                        label = label.capitalize()
                    li = xbmcgui.ListItem(label=label, iconImage=self.default_fanart)
                    li.setProperty('fanart_image', self.default_fanart)
                    # determine action route
                    action = actions['default']
                    if category in actions.keys():
                        action = actions[category]
                    # determine if the item should be selected
                    preselect_items.append((False, True)[category == self.get_main_menu_selection()])
                    url = build_url({'action': action, 'video_list_id': video_list_id, 'type': category})
                    xbmcplugin.addDirectoryItem(handle=self.plugin_handle, url=url, listitem=li, isFolder=True)

        # add recommendations/genres as subfolders
        # (save us some space on the home page)
        i18n_ids = {
            'recommendations': self.get_local_string(30001),
            'genres': self.get_local_string(30010)
        }
        for type in i18n_ids.keys():
            # determine if the lists have contents
            if len(video_list_ids[type]) > 0:
                # determine action route
                action = actions['default']
                if type in actions.keys():
                    action = actions[type]
                # determine if the item should be selected
                preselect_items.append((False, True)[type == self.get_main_menu_selection()])
                li_rec = xbmcgui.ListItem(
                    label=i18n_ids[type],
                    iconImage=self.default_fanart)
                li_rec.setProperty('fanart_image', self.default_fanart)
                url_rec = build_url({'action': action, 'type': type})
                xbmcplugin.addDirectoryItem(
                    handle=self.plugin_handle,
                    url=url_rec,
                    listitem=li_rec,
                    isFolder=True)

        # add search as subfolder
        action = actions['default']
        if 'search' in actions.keys():
            action = actions[type]
        li_rec = xbmcgui.ListItem(
            label=self.get_local_string(30011),
            iconImage=self.default_fanart)
        li_rec.setProperty('fanart_image', self.default_fanart)
        url_rec = build_url({'action': action, 'type': 'search'})
        xbmcplugin.addDirectoryItem(
            handle=self.plugin_handle,
            url=url_rec,
            listitem=li_rec,
            isFolder=True)

        # add exported as subfolder
        action = actions['default']
        if 'exported' in actions.keys():
            action = actions[type]
        li_rec = xbmcgui.ListItem(
            label=self.get_local_string(30048),
            iconImage=self.default_fanart)
        li_rec.setProperty('fanart_image', self.default_fanart)
        url_rec = build_url({'action': action, 'type': 'exported'})
        xbmcplugin.addDirectoryItem(
            handle=self.plugin_handle,
            url=url_rec,
            listitem=li_rec,
            isFolder=True)

        if self.show_update_db == 'true':
            # add updatedb as subfolder
            li_rec = xbmcgui.ListItem(
                label=self.get_local_string(30049),
                iconImage=self.default_fanart)
            li_rec.setProperty('fanart_image', self.default_fanart)
            url_rec = build_url({'action': 'updatedb'})
            xbmcplugin.addDirectoryItem(
                handle=self.plugin_handle,
                url=url_rec,
                listitem=li_rec,
                isFolder=True)

        # no sorting & close
        xbmcplugin.addSortMethod(
            handle=self.plugin_handle,
            sortMethod=xbmcplugin.SORT_METHOD_UNSORTED)
        xbmcplugin.setContent(
            handle=self.plugin_handle,
            content=CONTENT_FOLDER)
        xbmcplugin.endOfDirectory(self.plugin_handle)

        # (re)select the previously selected main menu entry
        idx = 1
        for item in preselect_items:
            idx += 1
            preselected_list_item = idx if item else None
        preselected_list_item = idx + 1 if self.get_main_menu_selection() == 'search' else preselected_list_item
        if preselected_list_item is not None:
            xbmc.executebuiltin('ActivateWindowAndFocus(%s, %s)' % (str(xbmcgui.Window(xbmcgui.getCurrentWindowId()).getFocusId()), str(preselected_list_item)))
        if not widget_display:
            self.set_custom_view(VIEW_FOLDER)
        return True

    def build_video_listing(self, video_list, actions, type, build_url,
                            has_more=False, start=0, current_video_list_id="",
                            widget_display=False):
        """
        Builds the video lists (my list, continue watching, etc.)
        contents Kodi screen

        Parameters
        ----------
        video_list_ids : :obj:`dict` of :obj:`str`
            List of video lists

        actions : :obj:`dict` of :obj:`str`
            Dictionary of actions to build subsequent routes

        type : :obj:`str`
            None or 'queue' f.e. when itÂ´s a special video lists

        build_url : :obj:`fn`
            Function to build the subsequent routes

        Returns
        -------
        bool
            List could be build
        """
        view = VIEW_FOLDER
        content = CONTENT_FOLDER
        listItems = list()
        for video_list_id in video_list:
            video = video_list[video_list_id]
            li = xbmcgui.ListItem(
                label=video['title'],
                iconImage=self.default_fanart)
            # add some art to the item
            li.setArt(self._generate_art_info(entry=video))
            # add list item info
            infos = self._generate_listitem_info(entry=video, li=li)
            self._generate_context_menu_items(entry=video, li=li)
            # lists can be mixed with shows & movies, therefor we need to check if its a movie, so play it right away
            if video['type'] == 'movie':
                # it´s a movie, so we need no subfolder & a route to play it
                isFolder = False
                maturity = video.get('maturity', {}).get('level', 999)
                needs_pin = (True, False)[int() >= 100]
                url = build_url({
                    'action': 'play_video',
                    'video_id': video_list_id,
                    'infoLabels': infos,
                    'pin': needs_pin})
                view = VIEW_MOVIE
                content = CONTENT_MOVIE
            else:
                # it´s a show, so we need a subfolder & route (for seasons)
                isFolder = True
                params = {
                    'action': actions[video['type']],
                    'show_id': video_list_id
                }
                params['pin'] = (True, False)[int(video.get('maturity', {}).get('level', 1001)) >= 1000]
                if 'tvshowtitle' in infos:
                    title = infos.get('tvshowtitle', '').encode('utf-8')
                    params['tvshowtitle'] = base64.urlsafe_b64encode(title)
                url = build_url(params)
                view = VIEW_SHOW
                content = CONTENT_SHOW
            listItems.append((url, li, isFolder))

        if has_more:
            li_more = xbmcgui.ListItem(label=self.get_local_string(30045))
            more_url = build_url({
                "action": "video_list",
                "type": type,
                "start": str(start),
                "video_list_id": current_video_list_id})
            listItems.append((more_url, li_more, True))

        xbmcplugin.addDirectoryItems(self.plugin_handle, listItems, len(listItems))

        xbmcplugin.addSortMethod(
            handle=self.plugin_handle,
            sortMethod=xbmcplugin.SORT_METHOD_UNSORTED)
        xbmcplugin.addSortMethod(
            handle=self.plugin_handle,
            sortMethod=xbmcplugin.SORT_METHOD_LABEL)
        xbmcplugin.addSortMethod(
            handle=self.plugin_handle,
            sortMethod=xbmcplugin.SORT_METHOD_TITLE)
        xbmcplugin.addSortMethod(
            handle=self.plugin_handle,
            sortMethod=xbmcplugin.SORT_METHOD_VIDEO_YEAR)
        xbmcplugin.addSortMethod(
            handle=self.plugin_handle,
            sortMethod=xbmcplugin.SORT_METHOD_GENRE)
        xbmcplugin.addSortMethod(
            handle=self.plugin_handle,
            sortMethod=xbmcplugin.SORT_METHOD_LASTPLAYED)
        xbmcplugin.setContent(
            handle=self.plugin_handle,
            content=content)

        xbmcplugin.endOfDirectory(self.plugin_handle)

        if not widget_display:
            self.set_custom_view(view)

        return True

    def build_video_listing_exported(self, content, build_url, widget_display=False):
        """Build list of exported movies / shows

        Parameters
        ----------
        content : :obj:`dict` of :obj:`str`
            List of video lists

        Returns
        -------
        bool
            List could be build
        """
        action = ['remove_from_library', self.get_local_string(30030), 'remove']

        li = xbmcgui.ListItem(
            label=self.get_local_string(30064),
            iconImage=self.default_fanart)
        li.setProperty('fanart_image', self.default_fanart)
        xbmcplugin.addDirectoryItem(
            handle=self.plugin_handle,
            url=build_url({'action': 'export-new-episodes','inbackground': True}),
            listitem=li,
            isFolder=False)
        listing = content
        for video in listing[0]:
            year = self.library.get_exported_movie_year(title=video)
            li = xbmcgui.ListItem(
                label=str(video)+' ('+str(year)+')',
                iconImage=self.default_fanart)
            li.setProperty('fanart_image', self.default_fanart)
            isFolder = False
            url = build_url({
                'action': 'removeexported',
                'title': str(video),
                'year': str(year),
                'type': 'movie'})
            art = {}
            image = self.library.get_previewimage(video)
            art.update({
                'landscape': image,
                'thumb': image
            })
            li.setArt(art)
            xbmcplugin.addDirectoryItem(
                handle=self.plugin_handle,
                url=url,
                listitem=li,
                isFolder=isFolder)

        for video in listing[2]:
            li = xbmcgui.ListItem(
                label=str(video),
                iconImage=self.default_fanart)
            li.setProperty('fanart_image', self.default_fanart)
            isFolder = False
            year = '0000'
            url = build_url({
                'action': 'removeexported',
                'title': str(str(video)),
                'year': str(year),
                'type': 'show'})
            art = {}
            image = self.library.get_previewimage(video)
            art.update({
                'landscape': image,
                'thumb': image
            })
            li.setArt(art)
            xbmcplugin.addDirectoryItem(
                handle=self.plugin_handle,
                url=url,
                listitem=li,
                isFolder=isFolder)

        xbmcplugin.addSortMethod(
            handle=self.plugin_handle,
            sortMethod=xbmcplugin.SORT_METHOD_UNSORTED)
        xbmcplugin.addSortMethod(
            handle=self.plugin_handle,
            sortMethod=xbmcplugin.SORT_METHOD_TITLE)
        xbmcplugin.setContent(
            handle=self.plugin_handle,
            content=CONTENT_FOLDER)
        xbmcplugin.endOfDirectory(self.plugin_handle)
        if not widget_display:
            self.set_custom_view(VIEW_EXPORTED)
        return True

    def build_search_result_folder(self, build_url, term, widget_display=False):
        """Add search result folder

        Parameters
        ----------
        build_url : :obj:`fn`
            Function to build the subsequent routes

        term : :obj:`str`
            Search term

        Returns
        -------
        :obj:`str`
            Search result folder URL
        """
        # add search result as subfolder
        li_rec = xbmcgui.ListItem(
            label='({})'.format(term),
            iconImage=self.default_fanart)
        li_rec.setProperty('fanart_image', self.default_fanart)
        url_rec = build_url({'action': 'search_result', 'term': term})
        xbmcplugin.addDirectoryItem(
            handle=self.plugin_handle,
            url=url_rec,
            listitem=li_rec,
            isFolder=True)
        xbmcplugin.addSortMethod(
            handle=self.plugin_handle,
            sortMethod=xbmcplugin.SORT_METHOD_UNSORTED)
        xbmcplugin.setContent(
            handle=self.plugin_handle,
            content=CONTENT_FOLDER)
        xbmcplugin.endOfDirectory(self.plugin_handle)
        if not widget_display:
            self.set_custom_view(VIEW_FOLDER)
        return url_rec

    def set_location(self, url, replace=False):
        """Set URL location

        Parameters
        ----------
        url : :obj:`str`
            Window URL

        ret : bool
            Return to location prior to activation

        Returns
        -------
        bool
            Window was activated
        """
        cmd = 'Container.Update({},{})'.format(url, str(replace))
        return xbmc.executebuiltin(cmd)

    def build_search_result_listing(self, video_list, actions, build_url):
        """Builds the search results list Kodi screen

        Parameters
        ----------
        video_list : :obj:`dict` of :obj:`str`
            List of videos or shows

        actions : :obj:`dict` of :obj:`str`
            Dictionary of actions to build subsequent routes

        build_url : :obj:`fn`
            Function to build the subsequent routes

        Returns
        -------
        bool
            List could be build
        """
        video_listing = self.build_video_listing(
            video_list=video_list,
            actions=actions,
            type='search',
            build_url=build_url)
        return video_listing

    def build_no_seasons_available(self):
        """Builds the season list screen if no seasons could be found

        Returns
        -------
        bool
            List could be build
        """
        self.dialogs.show_no_seasons_notify()
        xbmcplugin.endOfDirectory(self.plugin_handle)
        return True

    def build_no_search_results_available(self, build_url, action):
        """Builds the search results screen if no matches could be found

        Parameters
        ----------
        action : :obj:`str`
            Action paramter to build the subsequent routes

        build_url : :obj:`fn`
            Function to build the subsequent routes

        Returns
        -------
        bool
            List could be build
        """
        self.dialogs.show_no_search_results_notify()
        return xbmcplugin.endOfDirectory(self.plugin_handle)

    def build_user_sub_listing(self, video_list_ids, type, action, build_url,
                               widget_display=False):
        """
        Builds the video lists screen for user subfolders
        (genres & recommendations)

        Parameters
        ----------
        video_list_ids : :obj:`dict` of :obj:`str`
            List of video lists

        type : :obj:`str`
            List type (genre or recommendation)

        action : :obj:`str`
            Action paramter to build the subsequent routes

        build_url : :obj:`fn`
            Function to build the subsequent routes

        Returns
        -------
        bool
            List could be build
        """
        for video_list_id in video_list_ids:
            li = xbmcgui.ListItem(
                label=video_list_ids[video_list_id]['displayName'],
                iconImage=self.default_fanart)
            li.setProperty('fanart_image', self.default_fanart)
            url = build_url({'action': action, 'video_list_id': video_list_id})
            xbmcplugin.addDirectoryItem(
                handle=self.plugin_handle,
                url=url,
                listitem=li,
                isFolder=True)

        xbmcplugin.addSortMethod(
            handle=self.plugin_handle,
            sortMethod=xbmcplugin.SORT_METHOD_LABEL)
        xbmcplugin.setContent(
            handle=self.plugin_handle,
            content=CONTENT_FOLDER)
        xbmcplugin.endOfDirectory(self.plugin_handle)
        if not widget_display:
            self.set_custom_view(VIEW_FOLDER)
        return True

    def build_season_listing(self, seasons_sorted, build_url, widget_display=False):
        """Builds the season list screen for a show

        Parameters
        ----------
        seasons_sorted : :obj:`list` of :obj:`dict` of :obj:`str`
            Sorted list of season entries

        build_url : :obj:`fn`
            Function to build the subsequent routes

        Returns
        -------
        bool
            List could be build
        """
        for season in seasons_sorted:
            li = xbmcgui.ListItem(label=season['text'])
            # add some art to the item
            li.setArt(self._generate_art_info(entry=season))
            # add list item info
            infos = self._generate_listitem_info(
                entry=season,
                li=li,
                base_info={'mediatype': 'season'})
            self._generate_context_menu_items(entry=season, li=li)
            params = {'action': 'episode_list', 'season_id': season['id']}
            if 'tvshowtitle' in infos:
                title = infos.get('tvshowtitle', '').encode('utf-8')
                params['tvshowtitle'] = base64.urlsafe_b64encode(title)
            url = build_url(params)
            xbmcplugin.addDirectoryItem(
                handle=self.plugin_handle,
                url=url,
                listitem=li,
                isFolder=True)

        xbmcplugin.addSortMethod(
            handle=self.plugin_handle,
            sortMethod=xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.addSortMethod(
            handle=self.plugin_handle,
            sortMethod=xbmcplugin.SORT_METHOD_VIDEO_YEAR)
        xbmcplugin.addSortMethod(
            handle=self.plugin_handle,
            sortMethod=xbmcplugin.SORT_METHOD_LABEL)
        xbmcplugin.addSortMethod(
            handle=self.plugin_handle,
            sortMethod=xbmcplugin.SORT_METHOD_LASTPLAYED)
        xbmcplugin.addSortMethod(
            handle=self.plugin_handle,
            sortMethod=xbmcplugin.SORT_METHOD_TITLE)
        xbmcplugin.setContent(
            handle=self.plugin_handle,
            content=CONTENT_SEASON)
        xbmcplugin.endOfDirectory(self.plugin_handle)
        if not widget_display:
            self.set_custom_view(VIEW_SEASON)
        return True

    def build_episode_listing(self, episodes_sorted, build_url, widget_display=False):
        """Builds the episode list screen for a season of a show

        Parameters
        ----------
        episodes_sorted : :obj:`list` of :obj:`dict` of :obj:`str`
            Sorted list of episode entries

        build_url : :obj:`fn`
            Function to build the subsequent routes

        Returns
        -------
        bool
            List could be build
        """
        for episode in episodes_sorted:
            li = xbmcgui.ListItem(label=episode['title'])
            # add some art to the item
            li.setArt(self._generate_art_info(entry=episode))
            # add list item info
            infos = self._generate_listitem_info(
                entry=episode,
                li=li,
                base_info={'mediatype': 'episode'})
            self._generate_context_menu_items(entry=episode, li=li)
            maturity = episode.get('maturity', {}).get('maturityLevel', 999)
            needs_pin = (True, False)[int(maturity) >= 100]
            url = build_url({
                'action': 'play_video',
                'video_id': episode['id'],
                'start_offset': episode['bookmark'],
                'infoLabels': infos,
                'pin': needs_pin})
            xbmcplugin.addDirectoryItem(
                handle=self.plugin_handle,
                url=url,
                listitem=li,
                isFolder=False)

        xbmcplugin.addSortMethod(
            handle=self.plugin_handle,
            sortMethod=xbmcplugin.SORT_METHOD_EPISODE)
        xbmcplugin.addSortMethod(
            handle=self.plugin_handle,
            sortMethod=xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.addSortMethod(
            handle=self.plugin_handle,
            sortMethod=xbmcplugin.SORT_METHOD_VIDEO_YEAR)
        xbmcplugin.addSortMethod(
            handle=self.plugin_handle,
            sortMethod=xbmcplugin.SORT_METHOD_LABEL)
        xbmcplugin.addSortMethod(
            handle=self.plugin_handle,
            sortMethod=xbmcplugin.SORT_METHOD_LASTPLAYED)
        xbmcplugin.addSortMethod(
            handle=self.plugin_handle,
            sortMethod=xbmcplugin.SORT_METHOD_TITLE)
        xbmcplugin.addSortMethod(
            handle=self.plugin_handle,
            sortMethod=xbmcplugin.SORT_METHOD_DURATION)
        xbmcplugin.setContent(
            handle=self.plugin_handle,
            content=CONTENT_EPISODE)
        xbmcplugin.endOfDirectory(self.plugin_handle)
        if not widget_display:
            self.set_custom_view(VIEW_EPISODE)
        return True

    def play_item(self, video_id, start_offset=-1, infoLabels={}, tvshow_video_id=None, timeline_markers={}):
        """Plays a video

        Parameters
        ----------
        video_id : :obj:`str`
            ID of the video that should be played

        start_offset : :obj:`str`
            Offset to resume playback from (in seconds)

        infoLabels : :obj:`str`
            the listitem's infoLabels

        Returns
        -------
        bool
            List could be build
        """
        is_helper = inputstreamhelper.Helper('mpd', drm='widevine')
        if not is_helper.check_inputstream():
            return False

        # track play event
        self.track_event('playVideo')

        # inputstream addon properties
        port = str(self.nx_common.get_setting('msl_service_port'))
        msl_service_url = 'http://localhost:' + port
        msl_manifest_url = msl_service_url + '/manifest?id=' + video_id
        msl_manifest_url += '&dolby=' + self.nx_common.get_setting('enable_dolby_sound')
        msl_manifest_url += '&hevc=' +  self.nx_common.get_setting('enable_hevc_profiles')
        msl_manifest_url += '&hdr=' +  self.nx_common.get_setting('enable_hdr_profiles')
        msl_manifest_url += '&dolbyvision=' +  self.nx_common.get_setting('enable_dolbyvision_profiles')
        msl_manifest_url += '&vp9=' +  self.nx_common.get_setting('enable_vp9_profiles')

        play_item = xbmcgui.ListItem(path=msl_manifest_url)
        play_item.setContentLookup(False)
        play_item.setMimeType('application/dash+xml')
        play_item.setProperty(
            key=is_helper.inputstream_addon + '.stream_headers',
            value='user-agent=' + get_user_agent())
        play_item.setProperty(
            key=is_helper.inputstream_addon + '.license_type',
            value='com.widevine.alpha')
        play_item.setProperty(
            key=is_helper.inputstream_addon + '.manifest_type',
            value='mpd')
        play_item.setProperty(
            key=is_helper.inputstream_addon + '.license_key',
            value=msl_service_url + '/license?id=' + video_id + '||b{SSM}!b{SID}|')
        play_item.setProperty(
            key=is_helper.inputstream_addon + '.server_certificate',
            value='Cr0CCAMSEOVEukALwQ8307Y2+LVP+0MYh/HPkwUijgIwggEKAoIBAQDm875btoWUbGqQD8eAGuBlGY+Pxo8YF1LQR+Ex0pDONMet8EHslcZRBKNQ/09RZFTP0vrYimyYiBmk9GG+S0wB3CRITgweNE15cD33MQYyS3zpBd4z+sCJam2+jj1ZA4uijE2dxGC+gRBRnw9WoPyw7D8RuhGSJ95OEtzg3Ho+mEsxuE5xg9LM4+Zuro/9msz2bFgJUjQUVHo5j+k4qLWu4ObugFmc9DLIAohL58UR5k0XnvizulOHbMMxdzna9lwTw/4SALadEV/CZXBmswUtBgATDKNqjXwokohncpdsWSauH6vfS6FXwizQoZJ9TdjSGC60rUB2t+aYDm74cIuxAgMBAAE6EHRlc3QubmV0ZmxpeC5jb20SgAOE0y8yWw2Win6M2/bw7+aqVuQPwzS/YG5ySYvwCGQd0Dltr3hpik98WijUODUr6PxMn1ZYXOLo3eED6xYGM7Riza8XskRdCfF8xjj7L7/THPbixyn4mULsttSmWFhexzXnSeKqQHuoKmerqu0nu39iW3pcxDV/K7E6aaSr5ID0SCi7KRcL9BCUCz1g9c43sNj46BhMCWJSm0mx1XFDcoKZWhpj5FAgU4Q4e6f+S8eX39nf6D6SJRb4ap7Znzn7preIvmS93xWjm75I6UBVQGo6pn4qWNCgLYlGGCQCUm5tg566j+/g5jvYZkTJvbiZFwtjMW5njbSRwB3W4CrKoyxw4qsJNSaZRTKAvSjTKdqVDXV/U5HK7SaBA6iJ981/aforXbd2vZlRXO/2S+Maa2mHULzsD+S5l4/YGpSt7PnkCe25F+nAovtl/ogZgjMeEdFyd/9YMYjOS4krYmwp3yJ7m9ZzYCQ6I8RQN4x/yLlHG5RH/+WNLNUs6JAZ0fFdCmw=')
        play_item.setProperty(
            key='inputstreamaddon',
            value=is_helper.inputstream_addon)

        # check if we have a bookmark e.g. start offset position
        if int(start_offset) > 0:
            play_item.setProperty('StartOffset', str(start_offset) + '.0')
        # set infoLabels
        if len(infoLabels) > 0:
            play_item.setInfo('video', infoLabels)
        if len(infoLabels) == 0:
            infoLabels = self.library.read_metadata_file(video_id=video_id)
            art = self.library.read_artdata_file(video_id=video_id)
            play_item.setArt(art)
        play_item.setInfo('video', infoLabels)

        signal_data = {'timeline_markers': timeline_markers}

        if tvshow_video_id is not None:
            signal_data.update({'tvshow_video_id': tvshow_video_id})

        # check for content in kodi db
        if str(infoLabels) != 'None':
            if infoLabels['mediatype'] == 'episode':
                id = self.showtitle_to_id(title=infoLabels['tvshowtitle'])
                details = self.get_show_content_by_id(
                    showid=id,
                    showseason=infoLabels['season'],
                    showepisode=infoLabels['episode'])
            else:
                id = self.movietitle_to_id(title=infoLabels['title'])
                details = self.get_movie_content_by_id(movieid=id)

            if details is not False:
                if 'resume' in details[0]:
                    resume_point = details[0].pop('resume')
                    play_item.setProperty(
                        'StartOffset', str(resume_point))
                play_item.setInfo('video', details[0])
                play_item.setArt(details[1])
                signal_data.update({
                    'dbinfo': {
                        'dbid': details[0]['dbid'],
                        'dbtype': details[0]['mediatype'],
                        'playcount': details[0]['playcount']}})
                if infoLabels['mediatype'] == 'episode':
                    signal_data['dbinfo'].update({'tvshowid': id[0]})

        AddonSignals.sendSignal(Signals.PLAYBACK_INITIATED, signal_data)

        return xbmcplugin.setResolvedUrl(
            handle=self.plugin_handle,
            succeeded=True,
            listitem=play_item)

    def _generate_art_info(self, entry):
        """Adds the art info from an entry to a Kodi list item

        Parameters
        ----------
        entry : :obj:`dict` of :obj:`str`
            Entry that art dict should be generated for

        Returns
        -------
        :obj:`dict` of :obj:`str`
            Dictionary containing art info
        """
        art = {'fanart': self.default_fanart}
        # Cleanup art
        art.update({
            'landscape': '',
            'thumb': '',
            'fanart': '',
            'poster': '',
            'clearlogo': ''
        })
        if 'boxarts' in dict(entry).keys() and not isinstance(entry.get('boxarts'), dict):
            big = entry.get('boxarts', '')
            small = big
            poster = big
        if 'boxarts' in dict(entry).keys() and isinstance(entry.get('boxarts'), dict):
            big = entry.get('boxarts', {}).get('big')
            small = entry.get('boxarts', {}).get('small')
            poster = entry.get('boxarts', {}).get('poster')
            art.update({
                'poster': poster,
                'landscape': big or small,
                'thumb': big or small,
                'fanart': big or small
            })
            # Download image for exported listing
            if 'title' in entry:
                self.library.download_image_file(
                    title=entry['title'].encode('utf-8'),
                    url=str(big))

        if 'interesting_moment' in dict(entry).keys():
            if entry.get('type') == 'episode':
                art.update({'thumb': entry['interesting_moment'],
                            'landscape': entry['interesting_moment']})
            art.update({
                'fanart': entry['interesting_moment']
            })
        if 'artwork' in dict(entry).keys():
            art.update({
                'fanart': entry['artwork']
            })
        if 'clearlogo' in dict(entry).keys():
            art.update({'clearlogo': entry['clearlogo']})
        if 'thumb' in dict(entry).keys():
            art.update({'thumb': entry['thumb']})
        if 'fanart' in dict(entry).keys():
            art.update({'fanart': entry['fanart']})
        if 'poster' in dict(entry).keys():
            art.update({'poster': entry['poster']})
        vid_id = entry.get('id', entry.get('summary', {}).get('id'))
        self.library.write_artdata_file(video_id=str(vid_id), content=art)
        return art

    def _generate_listitem_info(self, entry, li, base_info={}):
        infos, li_infos = self._generate_entry_info(entry, base_info)
        li.setInfo('video', infos)
        if li_infos.get('is_playable'):
            li.setProperty('IsPlayable', 'true')
        if 'quality' in li_infos:
            li.addStreamInfo('video', li_infos['quality'])
        return infos

    def _generate_entry_info(self, entry, base_info):
        """Adds the item info from an entry to a Kodi list item

        Parameters
        ----------
        entry : :obj:`dict` of :obj:`str`
            Entry that info dict should be generated for

        base_info : :obj:`dict` of :obj:`str`
            Additional info that overrules the entry info

        Returns
        -------
        :obj:`dict` of :obj:`str`
            Dictionary containing info labels
        """
        infos = base_info
        li_infos = {}
        entry_keys = entry.keys()
        # Cleanup item info
        infos.update({
            'writer': '',
            'director': '',
            'genre': '',
            'mpaa': '',
            'rating': '',
            'plot': '',
            'duration': '',
            'season': '',
            'title': '',
            'tvshowtitle': '',
            'mediatype': 'movie',
            'playcount': '',
            'episode': '',
            'year': ''
        })

        if 'cast' in entry_keys and len(entry['cast']) > 0:
            infos.update({'cast': entry['cast']})
        if 'creators' in entry_keys and len(entry['creators']) > 0:
            infos.update({'writer': entry['creators'][0]})
        if 'directors' in entry_keys and len(entry['directors']) > 0:
            infos.update({'director': entry['directors'][0]})
        if 'genres' in entry_keys and len(entry['genres']) > 0:
            infos.update({'genre': entry['genres'][0]})
        if 'maturity' in entry_keys:
            if 'mpaa' in entry_keys:
                infos.update({'mpaa': entry['mpaa']})
            else:
                if entry.get('maturity', None) is not None:
                    if entry.get('maturity', {}).get('board') is not None and entry.get('maturity', {}).get('value') is not None:
                        infos.update({'mpaa': str(entry['maturity']['board'].encode('utf-8')) + '-' + str(entry['maturity']['value'].encode('utf-8'))})
        if 'rating' in entry_keys:
            infos.update({'rating': int(entry['rating']) * 2})
        if 'synopsis' in entry_keys:
            infos.update({'plot': entry['synopsis']})
        if 'plot' in entry_keys:
            infos.update({'plot': entry['plot']})
        if 'runtime' in entry_keys:
            infos.update({'duration': entry['runtime']})
        if 'duration' in entry_keys:
            infos.update({'duration': entry['duration']})
        if 'seasons_label' in entry_keys:
            infos.update({'season': entry['seasons_label']})
        if 'season' in entry_keys:
            infos.update({'season': entry['season']})
        if 'title' in entry_keys:
            infos.update({'title': entry['title']})
        if 'type' in entry_keys:
            if entry['type'] == 'movie' or entry['type'] == 'episode':
                li_infos['is_playable'] = True
            elif entry['type'] == 'show':
                infos.update({'tvshowtitle': entry['title']})
        if 'mediatype' in entry_keys:
            if (entry['mediatype'] == 'movie' or
                    entry['mediatype'] == 'episode'):
                li_infos['is_playable'] = True
                infos.update({'mediatype': entry['mediatype']})
        if 'watched' in entry_keys and entry.get('watched') is True:
            infos.update({'playcount': 1})
        else:
            del infos['playcount']
        if 'index' in entry_keys:
            infos.update({'episode': entry['index']})
        if 'episode' in entry_keys:
            infos.update({'episode': entry['episode']})
        if 'year' in entry_keys:
            infos.update({'year': entry['year']})
        if 'quality' in entry_keys:
            quality = {'width': '960', 'height': '540'}
            if entry['quality'] == '720':
                quality = {'width': '1280', 'height': '720'}
            if entry['quality'] == '1080':
                quality = {'width': '1920', 'height': '1080'}
            li_infos['quality'] = quality
        if 'tvshowtitle' in entry_keys:
            title = entry.get('tvshowtitle', '')
            if not isinstance(title, unicode):
                title = base64.urlsafe_b64decode(title).decode('utf-8')
            infos.update({'tvshowtitle': title})
        self.library.write_metadata_file(
            video_id=str(entry['id']), content=infos)
        return infos, li_infos

    def _generate_context_menu_items(self, entry, li):
        """Adds context menue items to a Kodi list item

        Parameters
        ----------
        entry : :obj:`dict` of :obj:`str`
            Entry that should be turned into a list item

        li : :obj:`XMBC.ListItem`
            Kodi list item instance
        Returns
        -------
        :obj:`XMBC.ListItem`
            Kodi list item instance
        """
        items = []
        action = {}
        entry_keys = entry.keys()

        # action item templates
        encoded_title = urlencode({'title': entry['title'].encode('utf-8')}) if 'title' in entry else ''
        url_tmpl = 'XBMC.RunPlugin(' + self.base_url + '?action=%action%&id=' + str(entry['id']) + '&' + encoded_title + ')'

        if not self._context_menu_actions:
            self._context_menu_actions = [
                ['export_to_library', self.get_local_string(30018), 'export'],
                ['remove_from_library', self.get_local_string(30030), 'remove'],
                ['update_the_library', self.get_local_string(30061), 'update'],
                ['rate_on_netflix', self.get_local_string(30019), 'rating'],
                ['remove_from_my_list', self.get_local_string(30020), 'remove_from_list'],
                ['add_to_my_list', self.get_local_string(30021), 'add_to_list']
            ]

        # build concrete action items
        for action_item in self._context_menu_actions:
            action.update({action_item[0]: [action_item[1], url_tmpl.replace('%action%', action_item[2])]})

        # add or remove the movie/show/season/episode from & to the users "My List"
        if 'in_my_list' in entry_keys:
            items.append(action['remove_from_my_list']) if entry['in_my_list'] else items.append(action['add_to_my_list'])
        elif 'queue' in entry_keys:
            items.append(action['remove_from_my_list']) if entry['queue'] else items.append(action['add_to_my_list'])
        elif 'my_list' in entry_keys:
            items.append(action['remove_from_my_list']) if entry['my_list'] else items.append(action['add_to_my_list'])
        # rate the movie/show/season/episode on Netflix
        items.append(action['rate_on_netflix'])

        # add possibility to export this movie/show/season/episode to a static/local library (and to remove it)
        if 'type' in entry_keys:
            # add/remove movie
            if entry['type'] == 'movie':
                action_type = 'remove_from_library' if self.library.movie_exists(title=entry['title'], year=entry.get('year', 0000)) else 'export_to_library'
                items.append(action[action_type])
                # Add update option
                if action_type == 'remove_from_library':
                    action_type = 'update_the_library'
                    items.append(action[action_type])
            if entry['type'] == 'show' and 'title' in entry_keys:
                action_type = 'remove_from_library' if self.library.show_exists(title=entry['title']) else 'export_to_library'
                items.append(action[action_type])
                # Add update option
                if action_type == 'remove_from_library':
                    action_type = 'update_the_library'
                    items.append(action[action_type])
        # add it to the item
        li.addContextMenuItems(items)
        #return li

    def movietitle_to_id(self, title):
        query = {
            "jsonrpc": "2.0",
            "method": "VideoLibrary.GetMovies",
            "params": {
                "properties": ["title"]
            },
            "id": "libMovies"
        }
        try:
            rpc_result = xbmc.executeJSONRPC(
                jsonrpccommand=json.dumps(query, encoding='utf-8'))
            json_result = json.loads(rpc_result)
            if 'result' in json_result and 'movies' in json_result['result']:
                json_result = json_result['result']['movies']
                for movie in json_result:
                    # Switch to ascii/lowercase and remove special chars and spaces
                    # to make sure best possible compare is possible
                    titledb = movie['title'].encode('ascii', 'ignore')
                    titledb = re.sub(r'[?|$|!|:|#|\.|\,|\'| ]', r'', titledb).lower().replace('-', '')
                    if '(' in titledb:
                        titledb = titledb.split('(')[0]
                    titlegiven = title.encode('ascii','ignore')
                    titlegiven = re.sub(r'[?|$|!|:|#|\.|\,|\'| ]', r'', titlegiven).lower().replace('-', '')
                    if '(' in titlegiven:
                        titlegiven = titlegiven.split('(')[0]
                    if titledb == titlegiven:
                        return movie['movieid']
            return '-1'
        except Exception:
            return '-1'

    def showtitle_to_id(self, title):
        query = {
            "jsonrpc": "2.0",
            "method": "VideoLibrary.GetTVShows",
            "params": {
                "properties": ["title", "genre"]
            },
            "id": "libTvShows"
        }
        try:
            rpc_result = xbmc.executeJSONRPC(
                jsonrpccommand=json.dumps(query, encoding='utf-8'))
            json_result = json.loads(rpc_result)
            if 'result' in json_result and 'tvshows' in json_result['result']:
                json_result = json_result['result']['tvshows']
                for tvshow in json_result:
                    # Switch to ascii/lowercase and
                    # remove special chars and spaces
                    # to make sure best possible compare is possible
                    titledb = tvshow['label'].encode('ascii', 'ignore')
                    titledb = re.sub(
                        pattern=r'[?|$|!|:|#|\.|\,|\'| ]',
                        repl=r'',
                        string=titledb).lower().replace('-', '')
                    if '(' in titledb:
                        titledb = titledb.split('(')[0]
                    titlegiven = title.encode('ascii', 'ignore')
                    titlegiven = re.sub(
                        pattern=r'[?|$|!|:|#|\.|\,|\'| ]',
                        repl=r'',
                        string=titlegiven).lower().replace('-', '')
                    if '(' in titlegiven:
                        titlegiven = titlegiven.split('(')[0]
                    if titledb == titlegiven:
                        return tvshow['tvshowid'], tvshow['genre']
            return '-1', ''
        except Exception:
            return '-1', ''

    def get_show_content_by_id(self, showid, showseason, showepisode):
        showseason = int(showseason)
        showepisode = int(showepisode)
        props = ["title", "showtitle", "season", "episode", "plot", "fanart",
                 "art", "resume", "playcount"]
        query = {
                "jsonrpc": "2.0",
                "method": "VideoLibrary.GetEpisodes",
                "params": {
                    "properties": props,
                    "tvshowid": int(showid[0])
                },
                "id": "1"
                }
        try:
            rpc_result = xbmc.executeJSONRPC(
                jsonrpccommand=json.dumps(query, encoding='utf-8'))
            json_result = json.loads(rpc_result)
            result = json_result.get('result', None)
            if result is not None and 'episodes' in result:
                result = result['episodes']
                for episode in result:
                    in_season = episode['season'] == showseason
                    in_episode = episode['episode'] == showepisode
                    if in_season and in_episode:
                        infos = {'mediatype': 'episode',
                                 'dbid': episode['episodeid'],
                                 'tvshowtitle': episode['showtitle'],
                                 'title': episode['title']}
                        if episode['resume']['position'] > 0:
                            infos['resume'] = episode['resume']['position']
                        infos.update({'playcount': episode.get('playcount', 0),
                                      'plot': episode['plot'],
                                      'genre': showid[1]}
                                     if episode.get('plot') else {})
                        art = {}
                        art.update({'fanart': episode['fanart']}
                                   if episode.get('fanart') else {})
                        if 'art' in episode:
                            _update_if_present(source_dict=episode['art'],
                                               source_att='thumb',
                                               target_dict=art,
                                               target_att='thumb')
                            _update_if_present(source_dict=episode['art'],
                                               source_att='tvshow.poster',
                                               target_dict=art,
                                               target_att='poster')
                            _update_if_present(source_dict=episode['art'],
                                               source_att='tvshow.banner',
                                               target_dict=art,
                                               target_att='banner')
                        return infos, art
            return False
        except Exception:
            return False

    def get_movie_content_by_id(self, movieid):
        query = {
                "jsonrpc": "2.0",
                "method": "VideoLibrary.GetMovieDetails",
                "params": {
                    "movieid": movieid,
                    "properties": [
                        "title",
                        "genre",
                        "plot",
                        "fanart",
                        "thumbnail",
                        "art",
                        "resume",
                        "playcount"]
                },
                "id": "libMovies"
            }
        try:
            rpc_result = xbmc.executeJSONRPC(
                jsonrpccommand=json.dumps(query, encoding='utf-8'))
            json_result = json.loads(rpc_result)
            result = json_result.get('result', None)
            if result is not None and 'moviedetails' in result:
                result = result.get('moviedetails', {})
                infos = {'mediatype': 'movie', 'dbid': movieid,
                         'title': result['title'],
                         'playcount': episode.get('playcount', 0)}
                if 'resume' in result:
                    infos.update('resume', result['resume'])
                if 'genre' in result and len(result['genre']) > 0:
                    infos.update({'genre': json_result['genre']})
                if 'plot' in result and len(result['plot']) > 0:
                    infos.update({'plot': result['plot']})
                art = {}
                if 'fanart' in result and len(result['fanart']) > 0:
                    art.update({'fanart': result['fanart']})
                if 'thumbnail' in result and len(result['thumbnail']) > 0:
                    art.update({'thumb': result['thumbnail']})
                if 'art' in json_result and len(result['art']['poster']) > 0:
                    art.update({'poster': result['art']['poster']})
                return infos, art
            return False
        except Exception:
            return False

    def get_local_string(self, string_id):
        """Returns the localized version of a string

        Parameters
        ----------
        string_id : :obj:`int`
            ID of the string that shoudl be fetched

        Returns
        -------
        :obj:`str`
            Requested string or empty string
        """
        src = xbmc if string_id < 30000 else self.nx_common.get_addon()
        locString = src.getLocalizedString(string_id)
        if isinstance(locString, unicode):
            locString = locString.encode('utf-8')
        return locString

    def track_event(self, event):
        """
        Send a tracking event if tracking is enabled
        :param event: the string idetifier of the event
        :return: None
        """
        # Check if tracking is enabled
        enable_tracking = (self.nx_common.get_setting('enable_tracking') == 'true')
        if enable_tracking:
            # Get or Create Tracking id
            tracking_id = self.nx_common.get_setting('tracking_id')
            if tracking_id is '':
                tracking_id = str(uuid4())
                self.nx_common.set_setting('tracking_id', tracking_id)
            # Send the tracking event
            tracker = Tracker.create('UA-46081640-5', client_id=tracking_id)
            tracker.send('event', event)
