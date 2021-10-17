# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Global addon constants

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
# Everything that is to be globally accessible must be defined in this module.
# Using the Kodi reuseLanguageInvoker feature, only the code in the addon.py or service.py module
# will be run every time the addon is called.
# All other modules (imports) are initialized only on the first invocation of the add-on.
import collections
import os
import sys
from urllib.parse import parse_qsl, unquote, urlparse

import xbmcaddon
from xbmcgui import Window


class GlobalVariables:
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
    path                Passes information to the called method
                          generally structured as follows: [func. name, menu id, context id]
    loco_contexts       Contexts used to obtain the list of contents (use only one context when loco_known = True)
    loco_known          If True, keys label_id/description_id/icon are ignored, these values are obtained from LoCo list
    label_id            The ID for the menu title
    description_id      Description info text
    icon                Set a default image
    view                Override the default "partial menu id" of view
    content_type        Override the default content type (CONTENT_SHOW)
    has_show_setting    Means that the menu has the show/hide settings, by default is True
    has_sort_setting    Means that the menu has the sort settings, by default is False
    no_use_cache        The cache will not be used to store the contents of the menu

    Explanation of function names in the 'path' key:
        video_list        Automatically gets the list_id by making a loco request,
                            the list_id search is made using the value specified on the loco_contexts key
        video_list_sorted To work must have a third argument on the path that is the context_id
                            or instead specified the key request_context_name
    '''
    MAIN_MENU_ITEMS = collections.OrderedDict([
        ('myList', {'path': ['video_list_sorted', 'myList'],
                    'loco_contexts': ['queue'],
                    'loco_known': True,
                    'request_context_name': 'mylist',
                    'view': VIEW_MYLIST,
                    'has_sort_setting': True,
                    'query_without_reference': True}),
        ('continueWatching', {'path': ['video_list', 'continueWatching'],
                              'loco_contexts': ['continueWatching'],
                              'loco_known': True}),
        ('newAndPopular', {'path': ['category_list', 'newAndPopular'],
                           'loco_contexts': ['comingSoon'],
                           'loco_known': False,
                           'label_id': 30700,
                           'description_id': 30146,
                           'icon': 'DefaultRecentlyAddedMovies.png'}),
        ('chosenForYou', {'path': ['video_list', 'chosenForYou'],
                          'loco_contexts': ['topTen'],
                          'loco_known': True}),
        ('recentlyAdded', {'path': ['video_list_sorted', 'recentlyAdded', '1592210'],
                           'loco_contexts': None,
                           'loco_known': False,
                           'request_context_name': 'genres',
                           'label_id': 30145,
                           'description_id': 30146,
                           'icon': 'DefaultRecentlyAddedMovies.png',
                           'has_sort_setting': True}),
        ('newRelease', {'path': ['video_list_sorted', 'newRelease'],
                        'loco_contexts': ['newRelease'],
                        'loco_known': True,
                        'request_context_name': 'newrelease',
                        'has_sort_setting': True,
                        'query_without_reference': True}),
        ('currentTitles', {'path': ['video_list', 'currentTitles'],
                           'loco_contexts': ['trendingNow'],
                           'loco_known': True}),
        ('mostViewed', {'path': ['video_list', 'mostViewed'],
                        'loco_contexts': ['popularTitles'],
                        'loco_known': True}),
        ('netflixOriginals', {'path': ['video_list_sorted', 'netflixOriginals', '839338'],
                              'loco_contexts': ['netflixOriginals'],
                              'loco_known': True,
                              'request_context_name': 'genres',
                              'has_sort_setting': True}),
        ('assistiveAudio', {'path': ['video_list_sorted', 'assistiveAudio', 'None'],
                            'loco_contexts': None,
                            'loco_known': False,
                            'request_context_name': 'assistiveAudio',
                            'label_id': 30163,
                            'description_id': 30164,
                            'icon': 'DefaultTVShows.png',
                            'has_sort_setting': True,
                            'query_without_reference': True}),
        ('recommendations', {'path': ['recommendations', 'recommendations'],
                             'loco_contexts': ['similars', 'becauseYouAdded', 'becauseYouLiked', 'watchAgain',
                                               'bigRow'],
                             'loco_known': False,
                             'label_id': 30001,
                             'description_id': 30094,
                             'icon': 'DefaultUser.png'}),
        ('tvshowsGenres', {'path': ['subgenres', 'tvshowsGenres', '83'],
                           'loco_contexts': None,
                           'loco_known': False,
                           'request_context_name': 'genres',  # Used for sub-menus
                           'label_id': 30174,
                           'description_id': None,
                           'icon': 'DefaultTVShows.png',
                           'has_sort_setting': True}),
        ('moviesGenres', {'path': ['subgenres', 'moviesGenres', '34399'],
                          'loco_contexts': None,
                          'loco_known': False,
                          'request_context_name': 'genres',  # Used for sub-menus
                          'label_id': 30175,
                          'description_id': None,
                          'icon': 'DefaultMovies.png',
                          'content_type': CONTENT_MOVIE,
                          'has_sort_setting': True}),
        ('tvshows', {'path': ['genres', 'tvshows', '83'],
                     'loco_contexts': None,
                     'loco_known': False,
                     'request_context_name': 'genres',  # Used for sub-menus
                     'label_id': 30095,
                     'description_id': None,
                     'icon': 'DefaultTVShows.png',
                     'has_sort_setting': True}),
        ('movies', {'path': ['genres', 'movies', '34399'],
                    'loco_contexts': None,
                    'loco_known': False,
                    'request_context_name': 'genres',  # Used for sub-menus
                    'label_id': 30096,
                    'description_id': None,
                    'icon': 'DefaultMovies.png',
                    'content_type': CONTENT_MOVIE,
                    'has_sort_setting': True}),
        ('genres', {'path': ['genres', 'genres'],
                    'loco_contexts': ['genre'],
                    'loco_known': False,
                    'request_context_name': 'genres',  # Used for sub-menus
                    'label_id': 30010,
                    'description_id': 30093,
                    'icon': 'DefaultGenre.png',
                    'has_sort_setting': True}),
        ('search', {'path': ['search', 'search'],
                    'loco_contexts': None,
                    'loco_known': False,
                    'label_id': 30400,
                    'description_id': 30092,
                    'icon': 'DefaultAddonsSearch.png',
                    'view': VIEW_SEARCH,
                    'has_sort_setting': True}),
        ('exported', {'path': ['exported', 'exported'],
                      'loco_contexts': None,
                      'loco_known': False,
                      'label_id': 30048,
                      'description_id': 30091,
                      'icon': 'DefaultHardDisk.png',
                      'view': VIEW_EXPORTED})
    ])

    MODE_DIRECTORY = 'directory'
    MODE_ACTION = 'action'
    MODE_PLAY = 'play'
    MODE_PLAY_STRM = 'play_strm'
    MODE_LIBRARY = 'library'
    MODE_KEYMAPS = 'keymaps'

    def __init__(self):
        """Do nothing on constructing the object"""
        # The class initialization (GlobalVariables) will only take place at the first initialization of this module
        # on subsequent add-on invocations (invoked by reuseLanguageInvoker) will have no effect.
        # Define here also any other variables necessary for the correct loading of the other project modules
        self.WND_KODI_HOME = Window(10000)  # Kodi home window
        self.IS_ADDON_FIRSTRUN = None
        self.ADDON = None
        self.ADDON_DATA_PATH = None
        self.DATA_PATH = None
        self.CACHE_MANAGEMENT = None
        self.CACHE_TTL = None
        self.CACHE_MYLIST_TTL = None
        self.CACHE_METADATA_TTL = None

    def init_globals(self, argv):
        """Initialized globally used module variables. Needs to be called at start of each plugin instance!"""
        # IS_ADDON_FIRSTRUN: specifies if the add-on has been initialized for the first time
        #                    (reuseLanguageInvoker not used yet)
        self.IS_ADDON_FIRSTRUN = self.IS_ADDON_FIRSTRUN is None
        self.IS_ADDON_EXTERNAL_CALL = False
        # xbmcaddon.Addon must be created at every instance otherwise it does not read any new changes to the settings
        self.ADDON = xbmcaddon.Addon()
        self.URL = urlparse(argv[0])
        self.REQUEST_PATH = unquote(self.URL[2][1:])
        try:
            self.PARAM_STRING = argv[2][1:]
        except IndexError:
            self.PARAM_STRING = ''
        self.REQUEST_PARAMS = dict(parse_qsl(self.PARAM_STRING))
        if self.IS_ADDON_FIRSTRUN:
            # Global variables that do not need to be generated at every instance
            self.ADDON_ID = self.ADDON.getAddonInfo('id')
            self.PLUGIN = self.ADDON.getAddonInfo('name')
            self.VERSION_RAW = self.ADDON.getAddonInfo('version')
            self.VERSION = remove_ver_suffix(self.VERSION_RAW)
            self.ICON = self.ADDON.getAddonInfo('icon')
            self.DEFAULT_FANART = self.ADDON.getAddonInfo('fanart')
            self.ADDON_DATA_PATH = self.ADDON.getAddonInfo('path')  # Add-on folder
            self.DATA_PATH = self.ADDON.getAddonInfo('profile')  # Add-on user data folder
            self.ADDON_PACKAGES_PATH = os.path.join(self.ADDON_DATA_PATH, 'packages')
            self.CACHE_PATH = os.path.join(self.DATA_PATH, 'cache')
            self.COOKIES_PATH = os.path.join(self.DATA_PATH, 'COOKIES')
            try:
                self.PLUGIN_HANDLE = int(argv[1])
                self.IS_SERVICE = False
                self.BASE_URL = f'{self.URL[0]}://{self.URL[1]}'
            except IndexError:
                self.PLUGIN_HANDLE = 0
                self.IS_SERVICE = True
                self.BASE_URL = f'plugin://{self.ADDON_ID}'
            from resources.lib.common.kodi_ops import KodiVersion
            self.KODI_VERSION = KodiVersion()
        # Initialize the log
        from resources.lib.utils.logging import LOG
        LOG.initialize(self.ADDON_ID, self.PLUGIN_HANDLE,
                       self.ADDON.getSettingBool('enable_debug'),
                       self.ADDON.getSettingBool('enable_timing'))
        # Add path of embedded packages (not supplied by Kodi) to python system directory
        if self.ADDON_PACKAGES_PATH not in sys.path:
            sys.path.insert(0, self.ADDON_PACKAGES_PATH)
        if self.IS_ADDON_FIRSTRUN:
            self.init_database()
            # Initialize the cache
            if self.IS_SERVICE:
                from resources.lib.services.cache_management import CacheManagement
                self.CACHE_MANAGEMENT = CacheManagement()
                self.CACHE = self.CACHE_MANAGEMENT
                from resources.lib.services.settings_monitor import SettingsMonitor
                self.SETTINGS_MONITOR = SettingsMonitor()
            else:
                from resources.lib.common.cache import Cache
                self.CACHE = Cache()
        self.IPC_OVER_HTTP = self.ADDON.getSettingBool('enable_ipc_over_http')

    def init_database(self):
        # Initialize local database
        import resources.lib.database.db_local as db_local
        self.LOCAL_DB = db_local.NFLocalDatabase()
        # Initialize shared database
        use_mysql = G.ADDON.getSettingBool('use_mysql')
        import resources.lib.database.db_shared as db_shared
        from resources.lib.common.exceptions import DBMySQLConnectionError, DBMySQLError
        try:
            shared_db_class = db_shared.get_shareddb_class(use_mysql=use_mysql)
            self.SHARED_DB = shared_db_class()
        except (DBMySQLConnectionError, DBMySQLError) as exc:
            import resources.lib.kodi.ui as ui
            if isinstance(exc, DBMySQLError):
                # There is a problem with the database
                ui.show_addon_error_info(exc)
            # The MySQL database cannot be reached, fallback to local SQLite database
            # When this code is called from addon, is needed apply the change also in the
            # service, so disabling it run the SettingsMonitor
            self.ADDON.setSettingBool('use_mysql', False)
            ui.show_notification(self.ADDON.getLocalizedString(30206), time=10000)
            shared_db_class = db_shared.get_shareddb_class()
            self.SHARED_DB = shared_db_class()

    def is_known_menu_context(self, context):
        """Return true if context are one of the menu with loco_known=True"""
        for _, data in self.MAIN_MENU_ITEMS.items():
            if data['loco_known']:
                if data['loco_contexts'][0] == context:
                    return True
        return False


def remove_ver_suffix(version):
    """Remove the codename suffix from version value"""
    import re
    pattern = re.compile(r'\+\w+\.\d$')  # Example: +matrix.1
    return re.sub(pattern, '', version)


# We initialize an instance importable of GlobalVariables from run_addon.py and run_service.py,
# where G.init_globals() MUST be called before you do anything else.
G = GlobalVariables()
