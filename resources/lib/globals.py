# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Global addon constants

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
# Everything that is to be globally accessible must be defined in this module
# and initialized in GlobalVariables.init_globals.
# When reusing Kodi languageInvokers, only the code in the main module
# (addon.py or service.py) will be run every time the addon is called.
# All other code executed on module level will only be executed once, when
# the module is first imported on the first addon invocation.
from __future__ import absolute_import, division, unicode_literals

import collections
import os
import sys

try:  # Python 3
    from urllib.parse import parse_qsl, unquote, urlparse
except ImportError:  # Python 2
    from urllib2 import unquote
    from urlparse import parse_qsl, urlparse

from future.utils import iteritems

import xbmc
import xbmcaddon


class GlobalVariables(object):
    """Encapsulation for global variables to work around quirks with
    Kodi's reuseLanguageInvoker behavior"""
    # pylint: disable=attribute-defined-outside-init
    # pylint: disable=invalid-name, too-many-instance-attributes

    # Values in the variables VIEW_* stand for a partial menu id,
    # contained in the settings xml, example 'profiles' stand for id 'viewmodeprofiles'
    VIEW_PROFILES = 'profiles'
    VIEW_MAINMENU = 'mainmenu'
    VIEW_MYLIST = 'mylist'
    VIEW_FOLDER = 'folder'
    VIEW_MOVIE = 'movie'
    VIEW_SHOW = 'show'
    VIEW_SEASON = 'season'
    VIEW_EPISODE = 'episode'
    VIEW_SEARCH = 'search'
    VIEW_EXPORTED = 'exported'

    CONTENT_IMAGES = 'images'
    CONTENT_FOLDER = 'files'
    CONTENT_MOVIE = 'movies'
    CONTENT_SHOW = 'tvshows'
    CONTENT_SEASON = 'seasons'
    CONTENT_EPISODE = 'episodes'

    '''
    --Main Menu key infos--
    path : passes information to the called method generally structured as follows: [func. name, menu id, context id]
    lolomo_contexts : contexts used to obtain the list of contents (use only one context when lolomo_known = True)
    lolomo_known : if True, keys label_id/description_id/icon are ignored, the values are obtained from lolomo list
    label_id : menu title
    description_id : description info text
    icon : set a default image
    view : override the default "partial menu id" of view
    content_type : override the default content type (CONTENT_SHOW)

    Explanation of function names in the 'path' key:
        video_list: automatically gets the list_id by making a lolomo request,
                    the list_id search is made using the value specified on the lolomo_contexts key
        video_list_sorted: to work must have a third argument on the path that is the context_id
                           or instead specified the key request_context_name
    '''
    MAIN_MENU_ITEMS = collections.OrderedDict([
        ('myList', {'path': ['video_list_sorted', 'myList'],
                    'lolomo_contexts': ['queue'],
                    'lolomo_known': True,
                    'request_context_name': 'mylist',
                    'view': VIEW_MYLIST}),
        ('continueWatching', {'path': ['video_list', 'continueWatching'],
                              'lolomo_contexts': ['continueWatching'],
                              'lolomo_known': True}),
        ('chosenForYou', {'path': ['video_list', 'chosenForYou'],
                          'lolomo_contexts': ['topTen'],
                          'lolomo_known': True}),
        ('recentlyAdded', {'path': ['video_list_sorted', 'recentlyAdded', '1592210'],
                           'lolomo_contexts': None,
                           'lolomo_known': False,
                           'request_context_name': 'genres',
                           'label_id': 30145,
                           'description_id': 30146,
                           'icon': 'DefaultRecentlyAddedMovies.png'}),
        ('newRelease', {'path': ['video_list_sorted', 'newRelease'],
                        'lolomo_contexts': ['newRelease'],
                        'lolomo_known': True,
                        'request_context_name': 'newrelease'}),
        ('currentTitles', {'path': ['video_list', 'currentTitles'],
                           'lolomo_contexts': ['trendingNow'],
                           'lolomo_known': True}),
        ('mostWatched', {'path': ['video_list', 'mostWatched'],  # Top 10 menu
                         'lolomo_contexts': ['mostWatched'],
                         'lolomo_known': True}),
        ('mostViewed', {'path': ['video_list', 'mostViewed'],
                        'lolomo_contexts': ['popularTitles'],
                        'lolomo_known': True}),
        ('netflixOriginals', {'path': ['video_list_sorted', 'netflixOriginals', '839338'],
                              'lolomo_contexts': ['netflixOriginals'],
                              'lolomo_known': True,
                              'request_context_name': 'genres'}),
        ('assistiveAudio', {'path': ['video_list_sorted', 'assistiveAudio', 'None'],
                            'lolomo_contexts': None,
                            'lolomo_known': False,
                            'request_context_name': 'assistiveAudio',
                            'label_id': 30163,
                            'description_id': 30164,
                            'icon': 'DefaultTVShows.png'}),
        ('recommendations', {'path': ['recommendations', 'recommendations'],
                             'lolomo_contexts': ['similars', 'becauseYouAdded', 'becauseYouLiked', 'watchAgain',
                                                 'bigRow'],
                             'lolomo_known': False,
                             'label_id': 30001,
                             'description_id': 30094,
                             'icon': 'DefaultUser.png'}),
        ('tvshowsGenres', {'path': ['subgenres', 'tvshowsGenres', '83'],
                           'lolomo_contexts': None,
                           'lolomo_known': False,
                           'request_context_name': 'genres',  # Used for sub-menus
                           'label_id': 30174,
                           'description_id': None,
                           'icon': 'DefaultTVShows.png'}),
        ('moviesGenres', {'path': ['subgenres', 'moviesGenres', '34399'],
                          'lolomo_contexts': None,
                          'lolomo_known': False,
                          'request_context_name': 'genres',  # Used for sub-menus
                          'label_id': 30175,
                          'description_id': None,
                          'icon': 'DefaultMovies.png',
                          'content_type': CONTENT_MOVIE}),
        ('tvshows', {'path': ['genres', 'tvshows', '83'],
                     'lolomo_contexts': None,
                     'lolomo_known': False,
                     'request_context_name': 'genres',  # Used for sub-menus
                     'label_id': 30095,
                     'description_id': None,
                     'icon': 'DefaultTVShows.png'}),
        ('movies', {'path': ['genres', 'movies', '34399'],
                    'lolomo_contexts': None,
                    'lolomo_known': False,
                    'request_context_name': 'genres',  # Used for sub-menus
                    'label_id': 30096,
                    'description_id': None,
                    'icon': 'DefaultMovies.png',
                    'content_type': CONTENT_MOVIE}),
        ('genres', {'path': ['genres', 'genres'],
                    'lolomo_contexts': ['genre'],
                    'lolomo_known': False,
                    'request_context_name': 'genres',  # Used for sub-menus
                    'label_id': 30010,
                    'description_id': 30093,
                    'icon': 'DefaultGenre.png'}),
        ('search', {'path': ['search', 'search'],
                    'lolomo_contexts': None,
                    'lolomo_known': False,
                    'label_id': 30011,
                    'description_id': 30092,
                    'icon': None,
                    'view': VIEW_SEARCH}),
        ('exported', {'path': ['exported', 'exported'],
                      'lolomo_contexts': None,
                      'lolomo_known': False,
                      'label_id': 30048,
                      'description_id': 30091,
                      'icon': 'DefaultHardDisk.png',
                      'view': VIEW_EXPORTED})
    ])

    MODE_DIRECTORY = 'directory'
    MODE_HUB = 'hub'
    MODE_ACTION = 'action'
    MODE_PLAY = 'play'
    MODE_LIBRARY = 'library'

    def __init__(self):
        """Do nothing on constructing the object"""
        # Define here any variables necessary for the correct loading of the modules
        self.IS_ADDON_FIRSTRUN = None
        self.ADDON = None
        self.ADDON_DATA_PATH = None
        self.DATA_PATH = None
        self.CACHE = None
        self.CACHE_MANAGEMENT = None
        self.CACHE_TTL = None
        self.CACHE_MYLIST_TTL = None
        self.CACHE_METADATA_TTL = None

    def init_globals(self, argv, reinitialize_database=False):
        """Initialized globally used module variables.
        Needs to be called at start of each plugin instance!
        This is an ugly hack because Kodi doesn't execute statements defined on
        module level if reusing a language invoker."""
        # IS_ADDON_FIRSTRUN specifies when the addon is at its first run (reuselanguageinvoker is not yet used)
        self.IS_ADDON_FIRSTRUN = self.IS_ADDON_FIRSTRUN is None
        self.IS_ADDON_EXTERNAL_CALL = False
        self.PY_IS_VER2 = sys.version_info.major == 2
        self.COOKIES = {}
        self.ADDON = xbmcaddon.Addon()
        self.ADDON_ID = self.py2_decode(self.ADDON.getAddonInfo('id'))
        self.PLUGIN = self.py2_decode(self.ADDON.getAddonInfo('name'))
        self.VERSION_RAW = self.py2_decode(self.ADDON.getAddonInfo('version'))
        self.VERSION = self.remove_ver_suffix(self.VERSION_RAW)
        self.DEFAULT_FANART = self.py2_decode(self.ADDON.getAddonInfo('fanart'))
        self.ICON = self.py2_decode(self.ADDON.getAddonInfo('icon'))
        self.ADDON_DATA_PATH = self.py2_decode(self.ADDON.getAddonInfo('path'))  # Addon folder
        self.DATA_PATH = self.py2_decode(self.ADDON.getAddonInfo('profile'))  # Addon user data folder

        # Add absolute paths of embedded py modules to python system directory
        module_paths = [
            os.path.join(self.ADDON_DATA_PATH, 'modules', 'mysql-connector-python')
        ]
        for path in module_paths:
            path = xbmc.translatePath(path)
            if path not in sys.path:
                sys.path.insert(0, g.py2_decode(path))

        self.CACHE_PATH = os.path.join(self.DATA_PATH, 'cache')
        self.COOKIE_PATH = os.path.join(self.DATA_PATH, 'COOKIE')
        self.URL = urlparse(argv[0])
        try:
            self.PLUGIN_HANDLE = int(argv[1])
            self.IS_SERVICE = False
            self.BASE_URL = '{scheme}://{netloc}'.format(scheme=self.URL[0],
                                                         netloc=self.URL[1])
        except IndexError:
            self.PLUGIN_HANDLE = 0
            self.IS_SERVICE = True
            self.BASE_URL = '{scheme}://{netloc}'.format(scheme='plugin',
                                                         netloc=self.ADDON_ID)
        self.PATH = g.py2_decode(unquote(self.URL[2][1:]))
        try:
            self.PARAM_STRING = argv[2][1:]
        except IndexError:
            self.PARAM_STRING = ''
        self.REQUEST_PARAMS = dict(parse_qsl(self.PARAM_STRING))
        self.reset_time_trace()
        self.TIME_TRACE_ENABLED = self.ADDON.getSettingBool('enable_timing')
        self.IPC_OVER_HTTP = self.ADDON.getSettingBool('enable_ipc_over_http')

        self._init_database(self.IS_ADDON_FIRSTRUN or reinitialize_database)

        self.settings_monitor_suspend(False)  # Reset the value in case of addon crash

        # Initialize the cache
        self.CACHE_TTL = self.ADDON.getSettingInt('cache_ttl') * 60
        self.CACHE_MYLIST_TTL = self.ADDON.getSettingInt('cache_mylist_ttl') * 60
        self.CACHE_METADATA_TTL = self.ADDON.getSettingInt('cache_metadata_ttl') * 24 * 60 * 60
        if self.IS_ADDON_FIRSTRUN:
            if self.IS_SERVICE:
                from resources.lib.services.cache.cache_management import CacheManagement
                self.CACHE_MANAGEMENT = CacheManagement()
            from resources.lib.common.cache import Cache
            self.CACHE = Cache()
            from resources.lib.common.kodiops import GetKodiVersion
            self.KODI_VERSION = GetKodiVersion()

    def _init_database(self, initialize):
        # Initialize local database
        if initialize:
            import resources.lib.database.db_local as db_local
            self.LOCAL_DB = db_local.NFLocalDatabase()
        # Initialize shared database
        use_mysql = g.ADDON.getSettingBool('use_mysql')
        if initialize or use_mysql:
            import resources.lib.database.db_shared as db_shared
            from resources.lib.database.db_exceptions import MySQLConnectionError, MySQLError
            try:
                shared_db_class = db_shared.get_shareddb_class(use_mysql=use_mysql)
                self.SHARED_DB = shared_db_class()
            except (MySQLConnectionError, MySQLError) as exc:
                import resources.lib.kodi.ui as ui
                if isinstance(exc, MySQLError):
                    # There is a problem with the database
                    ui.show_addon_error_info(exc)
                # The MySQL database cannot be reached, fallback to local SQLite database
                # When this code is called from addon, is needed apply the change also in the
                # service, so disabling it run the SettingsMonitor
                self.ADDON.setSettingBool('use_mysql', False)
                ui.show_notification(self.ADDON.getLocalizedString(30206), time=10000)
                shared_db_class = db_shared.get_shareddb_class()
                self.SHARED_DB = shared_db_class()

    def settings_monitor_suspend(self, is_suspended=True, at_first_change=False):
        """
        Suspends for the necessary time the settings monitor of the service
        that otherwise cause the reinitialization of global settings and possible consequent actions
        to settings changes or unnecessary checks when a setting will be changed.
        :param is_suspended: True/False - allows or denies the execution of the settings monitor
        :param at_first_change:
         True - monitor setting is automatically reactivated after the FIRST change to the settings
         False - monitor setting MUST BE REACTIVATED MANUALLY
        :return: None
        """
        if is_suspended and at_first_change:
            new_value = 'First'
        else:
            new_value = str(is_suspended)
        # Accepted values in string: First, True, False
        current_value = g.LOCAL_DB.get_value('suspend_settings_monitor', 'False')
        if new_value == current_value:
            return
        g.LOCAL_DB.set_value('suspend_settings_monitor', new_value)

    def settings_monitor_suspend_status(self):
        """
        Returns the suspend status of settings monitor
        """
        return g.LOCAL_DB.get_value('suspend_settings_monitor', 'False')

    def get_esn(self):
        """Get the generated esn or if set get the custom esn"""
        from resources.lib.database.db_utils import TABLE_SESSION
        custom_esn = g.ADDON.getSetting('esn')
        return custom_esn if custom_esn else g.LOCAL_DB.get_value('esn', '', table=TABLE_SESSION)

    def get_edge_esn(self):
        """Get a previously generated edge ESN from the settings or generate
        a new one if none exists"""
        return self.ADDON.getSetting('edge_esn') or self.generate_edge_esn()

    def generate_edge_esn(self):
        """Generate a random EDGE ESN and save it to the settings"""
        import random
        esn = ['NFCDIE-02-']
        possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        for _ in range(0, 30):
            esn.append(random.choice(possible))
        edge_esn = ''.join(esn)
        self.settings_monitor_suspend(True, True)
        self.ADDON.setSetting('edge_esn', edge_esn)
        return edge_esn

    def is_known_menu_context(self, context):
        """Return true if context are one of the menu with lolomo_known=True"""
        for menu_id, data in iteritems(self.MAIN_MENU_ITEMS):  # pylint: disable=unused-variable
            if data['lolomo_known']:
                if data['lolomo_contexts'][0] == context:
                    return True
        return False

    def flush_settings(self):
        """Reload the ADDON"""
        # pylint: disable=attribute-defined-outside-init
        self.ADDON = xbmcaddon.Addon()

    def reset_time_trace(self):
        """Reset current time trace info"""
        self.TIME_TRACE = []
        self.time_trace_level = -2

    def add_time_trace_level(self):
        """Add a level to the time trace"""
        self.time_trace_level += 2

    def remove_time_trace_level(self):
        """Remove a level from the time trace"""
        self.time_trace_level -= 2

    def py2_decode(self, value, encoding='utf-8'):
        """Decode text only on python 2"""
        # To remove when Kodi 18 support is over / Py2 dead
        if self.PY_IS_VER2:
            return value.decode(encoding)
        return value

    def py2_encode(self, value):
        """Encode text only on python 2"""
        # To remove when Kodi 18 support is over / Py2 dead
        if self.PY_IS_VER2:
            return value.encode('utf-8')
        return value

    @staticmethod
    def remove_ver_suffix(version):
        """Remove the codename suffix from version value"""
        import re
        pattern = re.compile(r'\+\w+\.\d$')  # Example: +matrix.1
        return re.sub(pattern, '', version)


# pylint: disable=invalid-name
# This will have no effect most of the time, as it doesn't seem to be executed
# on subsequent addon invocations when reuseLanguageInvoker is being used.
# We initialize an empty instance so the instance is importable from run_addon.py
# and run_service.py, where g.init_globals(sys.argv) MUST be called before doing
# anything else (even BEFORE OTHER IMPORTS from this addon)
g = GlobalVariables()
