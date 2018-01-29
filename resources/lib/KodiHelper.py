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
from Cryptodome import Random
from os.path import join, isfile
from Cryptodome.Cipher import AES
from Cryptodome.Util import Padding
import xbmc
import xbmcgui
import xbmcplugin
import inputstreamhelper
from xbmcaddon import Addon
from resources.lib.MSL import MSL
from resources.lib.kodi.Dialogs import Dialogs
from utils import get_user_agent, uniq_id
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


class KodiHelper(object):
    """
    Consumes all the configuration data from Kodi as well as
    turns data into lists of folders and videos"""

    def __init__(self, plugin_handle=None, base_url=None):
        """
        Fetches all needed info from Kodi &
        configures the baseline of the plugin

        Parameters
        ----------
        plugin_handle : :obj:`int`
            Plugin handle

        base_url : :obj:`str`
            Plugin base url
        """
        addon = self.get_addon()
        raw_data_path = 'special://profile/addon_data/service.msl'
        data_path = xbmc.translatePath(raw_data_path)
        self.plugin_handle = plugin_handle
        self.base_url = base_url
        self.plugin = addon.getAddonInfo('name')
        self.version = addon.getAddonInfo('version')
        self.base_data_path = xbmc.translatePath(addon.getAddonInfo('profile'))
        self.home_path = xbmc.translatePath('special://home')
        self.plugin_path = addon.getAddonInfo('path')
        self.cookie_path = self.base_data_path + 'COOKIE'
        self.data_path = self.base_data_path + 'DATA'
        self.config_path = join(self.base_data_path, 'config')
        self.msl_data_path = data_path.decode('utf-8') + '/'
        self.verb_log = addon.getSetting('logging') == 'true'
        self.custom_export_name = addon.getSetting('customexportname')
        self.show_update_db = addon.getSetting('show_update_db')
        self.default_fanart = addon.getAddonInfo('fanart')
        self.bs = 32
        self.crypt_key = uniq_id()
        self.library = None
        self.setup_memcache()
        self.dialogs = Dialogs(
            get_local_string=self.get_local_string,
            custom_export_name=self.custom_export_name)

    def get_addon(self):
        """Returns a fresh addon instance"""
        return Addon()

    def check_folder_path(self, path):
        """
        Check if folderpath ends with path delimator
        If not correct it (makes sure xbmcvfs.exists is working correct)
        """
        if isinstance(path, unicode):
            check = path.encode('ascii', 'ignore')
            if '/' in check and not str(check).endswith('/'):
                end = u'/'
                path = path + end
                return path
            if '\\' in check and not str(check).endswith('\\'):
                end = u'\\'
                path = path + end
                return path
        if '/' in path and not str(path).endswith('/'):
            path = path + '/'
            return path
        if '\\' in path and not str(path).endswith('\\'):
            path = path + '\\'
            return path

    def refresh(self):
        """Refresh the current list"""
        return xbmc.executebuiltin('Container.Refresh')

    def set_setting(self, key, value):
        """Public interface for the addons setSetting method

        Returns
        -------
        bool
            Setting could be set or not
        """
        return self.get_addon().setSetting(key, value)

    def get_setting(self, key):
        """Public interface to the addons getSetting method

        Returns
        -------
        Returns setting key
        """
        return self.get_addon().getSetting(key)

    def toggle_adult_pin(self):
        """Toggles the adult pin setting"""
        addon = self.get_addon()
        adultpin_enabled = False
        raw_adultpin_enabled = addon.getSetting('adultpin_enable')
        if raw_adultpin_enabled == 'true' or raw_adultpin_enabled == 'True':
            adultpin_enabled = True
        if adultpin_enabled is False:
            return addon.setSetting('adultpin_enable', 'True')
        return addon.setSetting('adultpin_enable', 'False')

    def get_credentials(self):
        """Returns the users stored credentials

        Returns
        -------
        :obj:`dict` of :obj:`str`
            The users stored account data
        """
        addon = self.get_addon()
        email = addon.getSetting('email')
        password = addon.getSetting('password')

        # soft migration for existing credentials
        # base64 can't contain `@` chars
        if '@' in email:
            addon.setSetting('email', self.encode(raw=email))
            addon.setSetting('password', self.encode(raw=password))
            return {
                'email': self.get_addon().getSetting('email'),
                'password': self.get_addon().getSetting('password')
            }

        # if everything is fine, we decode the values
        if '' != email or '' != password:
            return {
                'email': self.decode(enc=email),
                'password': self.decode(enc=password)
            }

        # if email is empty, we return an empty map
        return {
            'email': '',
            'password': ''
        }

    def encode(self, raw):
        """
        Encodes data

        :param data: Data to be encoded
        :type data: str
        :returns:  string -- Encoded data
        """
        raw = Padding.pad(data_to_pad=raw, block_size=self.bs)
        iv = Random.new().read(AES.block_size)
        cipher = AES.new(self.crypt_key, AES.MODE_CBC, iv)
        return base64.b64encode(iv + cipher.encrypt(raw))

    def decode(self, enc):
        """
        Decodes data

        :param data: Data to be decoded
        :type data: str
        :returns:  string -- Decoded data
        """
        enc = base64.b64decode(enc)
        iv = enc[:AES.block_size]
        cipher = AES.new(self.crypt_key, AES.MODE_CBC, iv)
        decoded = Padding.unpad(
            padded_data=cipher.decrypt(enc[AES.block_size:]),
            block_size=self.bs).decode('utf-8')
        return decoded

    def get_esn(self):
        """
        Returns the esn from settings
        """
        return self.get_addon().getSetting('esn')

    def set_esn(self, esn):
        """
        Returns the esn from settings
        """
        stored_esn = self.get_esn()
        if not stored_esn and esn:
            self.set_setting('esn', esn)
            self.delete_manifest_data()
            return esn
        return stored_esn

    def delete_manifest_data(self):
        if isfile(self.msl_data_path + 'msl_data.json'):
            remove(self.msl_data_path + 'msl_data.json')
        if isfile(self.msl_data_path + 'manifest.json'):
            remove(self.msl_data_path + 'manifest.json')
        msl = MSL(kodi_helper=self)
        msl.perform_key_handshake()
        msl.save_msl_data()

    def get_dolby_setting(self):
        """
        Returns if the dolby sound is enabled
        :return: bool - Dolby Sourrind profile setting is enabled
        """
        use_dolby = False
        setting = self.get_addon().getSetting('enable_dolby_sound')
        if setting == 'true' or setting == 'True':
            use_dolby = True
        return use_dolby

    def use_hevc(self):
        """
        Checks if HEVC profiles should be used
        :return: bool - HEVC profile setting is enabled
        """
        use_hevc = False
        setting = self.get_addon().getSetting('enable_hevc_profiles')
        if setting == 'true' or setting == 'True':
            use_hevc = True
        return use_hevc

    def get_custom_library_settings(self):
        """Returns the settings in regards to the custom library folder(s)

        Returns
        -------
        :obj:`dict` of :obj:`str`
            The users library settings
        """
        addon = self.get_addon()
        return {
            'enablelibraryfolder': addon.getSetting('enablelibraryfolder'),
            'customlibraryfolder': addon.getSetting('customlibraryfolder')
        }

    def get_ssl_verification_setting(self):
        """
        Returns the setting that describes if we should
        verify the ssl transport when loading data

        Returns
        -------
        bool
            Verify or not
        """
        return self.get_addon().getSetting('ssl_verification') == 'true'

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
            (folder, movie, show, season, episode, login)

        """
        custom_view = self.get_addon().getSetting('customview')
        if custom_view == 'true':
            view = int(self.get_addon().getSetting('viewmode' + content))
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
        self.set_setting('autologin_user', autologin_user)
        self.set_setting('autologin_id', autologin_id)
        self.set_setting('autologin_enable', 'True')
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
        return xbmcplugin.endOfDirectory(handle=self.plugin_handle)

    def build_main_menu_listing(self, video_list_ids, user_list_order, actions, build_url):
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
        xbmcplugin.endOfDirectory(self.plugin_handle)

        # (re)select the previously selected main menu entry
        idx = 1
        for item in preselect_items:
            idx += 1
            preselected_list_item = idx if item else None
        preselected_list_item = idx + 1 if self.get_main_menu_selection() == 'search' else preselected_list_item
        if preselected_list_item is not None:
            xbmc.executebuiltin('ActivateWindowAndFocus(%s, %s)' % (str(xbmcgui.Window(xbmcgui.getCurrentWindowId()).getFocusId()), str(preselected_list_item)))
        self.set_custom_view(VIEW_FOLDER)
        return True

    def build_video_listing(self, video_list, actions, type, build_url, has_more=False, start=0, current_video_list_id=""):
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
        for video_list_id in video_list:
            video = video_list[video_list_id]
            li = xbmcgui.ListItem(
                label=video['title'],
                iconImage=self.default_fanart)
            # add some art to the item
            li = self._generate_art_info(entry=video, li=li)
            # add list item info
            li, infos = self._generate_entry_info(entry=video, li=li)
            li = self._generate_context_menu_items(entry=video, li=li)
            # lists can be mixed with shows & movies, therefor we need to check if its a movie, so play it right away
            if video_list[video_list_id]['type'] == 'movie':
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
            xbmcplugin.addDirectoryItem(
                handle=self.plugin_handle,
                url=url,
                listitem=li,
                isFolder=isFolder)

        if has_more:
            li_more = xbmcgui.ListItem(label=self.get_local_string(30045))
            more_url = build_url({
                "action": "video_list",
                "type": type,
                "start": str(start),
                "video_list_id": current_video_list_id})
            xbmcplugin.addDirectoryItem(
                handle=self.plugin_handle,
                url=more_url,
                listitem=li_more,
                isFolder=True)

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
        xbmcplugin.endOfDirectory(self.plugin_handle)
        self.set_custom_view(view)
        return True

    def build_video_listing_exported(self, content, build_url):
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
        xbmcplugin.endOfDirectory(self.plugin_handle)
        self.set_custom_view(VIEW_FOLDER)
        return True

    def build_search_result_folder(self, build_url, term):
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
        xbmcplugin.endOfDirectory(self.plugin_handle)
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

    def build_user_sub_listing(self, video_list_ids, type, action, build_url):
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
        xbmcplugin.endOfDirectory(self.plugin_handle)
        self.set_custom_view(VIEW_FOLDER)
        return True

    def build_season_listing(self, seasons_sorted, build_url):
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
            li = self._generate_art_info(entry=season, li=li)
            # add list item info
            li, infos = self._generate_entry_info(
                entry=season,
                li=li,
                base_info={'mediatype': 'season'})
            li = self._generate_context_menu_items(entry=season, li=li)
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
        xbmcplugin.endOfDirectory(self.plugin_handle)
        self.set_custom_view(VIEW_SEASON)
        return True

    def build_episode_listing(self, episodes_sorted, build_url):
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
            li = self._generate_art_info(entry=episode, li=li)
            # add list item info
            li, infos = self._generate_entry_info(
                entry=episode,
                li=li,
                base_info={'mediatype': 'episode'})
            li = self._generate_context_menu_items(entry=episode, li=li)
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
        xbmcplugin.endOfDirectory(self.plugin_handle)
        self.set_custom_view(VIEW_EPISODE)
        return True

    def play_item(self, esn, video_id, start_offset=-1, infoLabels={}):
        """Plays a video

        Parameters
        ----------
        esn : :obj:`str`
            ESN needed for Widevine/Inputstream

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
        self.set_esn(esn)
        addon = self.get_addon()
        is_helper = inputstreamhelper.Helper('mpd', drm='widevine')
        if not is_helper.check_inputstream():
            return False

        # track play event
        self.track_event('playVideo')

        # check esn in settings
        settings_esn = str(addon.getSetting('esn'))
        if len(settings_esn) == 0:
            addon.setSetting('esn', str(esn))

        # inputstream addon properties
        port = str(addon.getSetting('msl_service_port'))
        msl_service_url = 'http://localhost:' + port
        play_item = xbmcgui.ListItem(
            path=msl_service_url + '/manifest?id=' + video_id)
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

        # check for content in kodi db
        if str(infoLabels) != 'None':
            if infoLabels['mediatype'] == 'episode':
                id = self.showtitle_to_id(title=infoLabels['tvshowtitle'])
                details = self.get_show_content_by_id(
                    showid=id,
                    showseason=infoLabels['season'],
                    showepisode=infoLabels['episode'])
                if details is not False:
                    play_item.setInfo('video', details[0])
                    play_item.setArt(details[1])
            if infoLabels['mediatype'] != 'episode':
                id = self.movietitle_to_id(title=infoLabels['title'])
                details = self.get_movie_content_by_id(movieid=id)
                if details is not False:
                    play_item.setInfo('video', details[0])
                    play_item.setArt(details[1])

        resolved = xbmcplugin.setResolvedUrl(
            handle=self.plugin_handle,
            succeeded=True,
            listitem=play_item)
        return resolved

    def _generate_art_info(self, entry, li):
        """Adds the art info from an entry to a Kodi list item

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
        art = {'fanart': self.default_fanart}
        # Cleanup art
        art.update({
            'landscape': '',
            'thumb': '',
            'fanart': '',
            'poster': ''
        })
        self.log(entry)
        if 'boxarts' in dict(entry).keys() and not isinstance(entry.get('boxarts'), dict):
            big = entry.get('boxarts', '')
            small = big
        if 'boxarts' in dict(entry).keys() and isinstance(entry.get('boxarts'), dict):
            big = entry.get('boxarts', {}).get('big')
            small = entry.get('boxarts', {}).get('small')
            art.update({
                'poster': big or small,
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
            art.update({
                'poster': entry['interesting_moment'],
                'fanart': entry['interesting_moment']
            })
        if 'thumb' in dict(entry).keys():
            art.update({'thumb': entry['thumb']})
        if 'fanart' in dict(entry).keys():
            art.update({'fanart': entry['fanart']})
        if 'poster' in dict(entry).keys():
            art.update({'poster': entry['poster']})
        li.setArt(art)
        vid_id = entry.get('id', entry.get('summary', {}).get('id'))
        self.library.write_artdata_file(video_id=str(vid_id), content=art)
        return li

    def _generate_entry_info(self, entry, li, base_info={}):
        """Adds the item info from an entry to a Kodi list item

        Parameters
        ----------
        entry : :obj:`dict` of :obj:`str`
            Entry that should be turned into a list item

        li : :obj:`XMBC.ListItem`
            Kodi list item instance

        base_info : :obj:`dict` of :obj:`str`
            Additional info that overrules the entry info

        Returns
        -------
        :obj:`XMBC.ListItem`
            Kodi list item instance
        """
        infos = base_info
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
            'mediatype': '',
            'playcount': '',
            'episode': '',
            'year': '',
            'tvshowtitle': ''
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
                li.setProperty('IsPlayable', 'true')
            elif entry['type'] == 'show':
                infos.update({'tvshowtitle': entry['title']})
        if 'mediatype' in entry_keys:
            if entry['mediatype'] == 'movie' or entry['mediatype'] == 'episode':
                li.setProperty('IsPlayable', 'true')
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
            li.addStreamInfo('video', quality)
        if 'tvshowtitle' in entry_keys:
            title = base64.urlsafe_b64decode(entry.get('tvshowtitle', ''))
            infos.update({'tvshowtitle': title.decode('utf-8')})
        li.setInfo('video', infos)
        self.library.write_metadata_file(video_id=str(entry['id']), content=infos)
        return li, infos

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
        actions = [
            ['export_to_library', self.get_local_string(30018), 'export'],
            ['remove_from_library', self.get_local_string(30030), 'remove'],
            ['update_the_library', self.get_local_string(30061), 'update'],
            ['rate_on_netflix', self.get_local_string(30019), 'rating'],
            ['remove_from_my_list', self.get_local_string(30020), 'remove_from_list'],
            ['add_to_my_list', self.get_local_string(30021), 'add_to_list']
        ]

        # build concrete action items
        for action_item in actions:
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
        return li

    def log(self, msg, level=xbmc.LOGDEBUG):
        """Adds a log entry to the Kodi log

        Parameters
        ----------
        msg : :obj:`str`
            Entry that should be turned into a list item

        level : :obj:`int`
            Kodi log level
        """
        if isinstance(msg, unicode):
            msg = msg.encode('utf-8')
        xbmc.log('[%s] %s' % (self.plugin, msg.__str__()), level)

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
        src = xbmc if string_id < 30000 else self.get_addon()
        locString = src.getLocalizedString(string_id)
        if isinstance(locString, unicode):
            locString = locString.encode('utf-8')
        return locString

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
        props = ["season", "episode", "plot", "fanart", "art"]
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
                        infos = {}
                        if 'plot' in episode and len(episode['plot']) > 0:
                            infos.update({
                                'plot': episode['plot'],
                                'genre': showid[1]})
                        art = {}
                        if 'fanart' in episode and len(episode['fanart']) > 0:
                            art.update({'fanart': episode['fanart']})
                        if 'art' in episode and len(episode['art']['season.poster']) > 0:
                            art.update({
                                'thumb': episode['art']['season.poster']})
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
                        "genre",
                        "plot",
                        "fanart",
                        "thumbnail",
                        "art"]
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
                infos = {}
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

    def set_library(self, library):
        """Adds an instance of the Library class

        Parameters
        ----------
        library : :obj:`Library`
            instance of the Library class
        """
        self.library = library

    def track_event(self, event):
        """
        Send a tracking event if tracking is enabled
        :param event: the string idetifier of the event
        :return: None
        """
        addon = self.get_addon()
        # Check if tracking is enabled
        enable_tracking = (addon.getSetting('enable_tracking') == 'true')
        if enable_tracking:
            # Get or Create Tracking id
            tracking_id = addon.getSetting('tracking_id')
            if tracking_id is '':
                tracking_id = str(uuid4())
                addon.setSetting('tracking_id', tracking_id)
            # Send the tracking event
            tracker = Tracker.create('UA-46081640-5', client_id=tracking_id)
            tracker.send('event', event)
