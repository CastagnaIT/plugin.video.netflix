# -*- coding: utf-8 -*-
"""Global addon constants.
Everything that is to be globally accessible must be defined in this module
and initialized in GlobalVariables.init_globals.
When reusing Kodi languageInvokers, only the code in the main module
(addon.py or service.py) will be run every time the addon is called.
All other code executed on module level will only be executed once, when
the module is first imported on the first addon invocation."""
from __future__ import unicode_literals

import os
import sys
from urlparse import urlparse, parse_qsl
from urllib import unquote

import collections
import xbmc
import xbmcaddon
import xbmcvfs

import resources.lib.cache as cache


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
                             'lolomo_contexts': ['similars', 'becauseYouAdded'],
                             'lolomo_known': False,
                             'label_id': 30001,
                             'description_id': 30094,
                             'icon': 'DefaultUser.png',
                             'content_type': CONTENT_FOLDER}),
        ('tvshowsGenres', {'path': ['subgenres', 'tvshowsGenres', '83'],
                           'lolomo_contexts': None,
                           'lolomo_known': False,
                           'request_context_name': 'genres',  # Used for sub-menus
                           'label_id': 30174,
                           'description_id': None,
                           'icon': 'DefaultTVShows.png',
                           'content_type': CONTENT_FOLDER}),
        ('moviesGenres', {'path': ['subgenres', 'moviesGenres', '34399'],
                          'lolomo_contexts': None,
                          'lolomo_known': False,
                          'request_context_name': 'genres',  # Used for sub-menus
                          'label_id': 30175,
                          'description_id': None,
                          'icon': 'DefaultMovies.png',
                          'content_type': CONTENT_FOLDER}),
        ('tvshows', {'path': ['genres', 'tvshows', '83'],
                     'lolomo_contexts': None,
                     'lolomo_known': False,
                     'request_context_name': 'genres',  # Used for sub-menus
                     'label_id': 30095,
                     'description_id': None,
                     'icon': 'DefaultTVShows.png',
                     'content_type': CONTENT_FOLDER}),
        ('movies', {'path': ['genres', 'movies', '34399'],
                    'lolomo_contexts': None,
                    'lolomo_known': False,
                    'request_context_name': 'genres',  # Used for sub-menus
                    'label_id': 30096,
                    'description_id': None,
                    'icon': 'DefaultMovies.png',
                    'content_type': CONTENT_FOLDER}),
        ('genres', {'path': ['genres', 'genres'],
                    'lolomo_contexts': ['genre'],
                    'lolomo_known': False,
                    'request_context_name': 'genres',  # Used for sub-menus
                    'label_id': 30010,
                    'description_id': 30093,
                    'icon': 'DefaultGenre.png',
                    'content_type': CONTENT_FOLDER}),
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
        pass

    def init_globals(self, argv):
        """Initialized globally used module variables.
        Needs to be called at start of each plugin instance!
        This is an ugly hack because Kodi doesn't execute statements defined on
        module level if reusing a language invoker."""
        self._library = None
        self.SETTINGS_MONITOR_IGNORE = False
        self.COOKIES = {}
        self.ADDON = xbmcaddon.Addon()
        self.ADDON_ID = self.ADDON.getAddonInfo('id')
        self.PLUGIN = self.ADDON.getAddonInfo('name')
        self.VERSION = self.ADDON.getAddonInfo('version')
        self.DEFAULT_FANART = self.ADDON.getAddonInfo('fanart')
        self.ICON = self.ADDON.getAddonInfo('icon')
        self.ADDON_DATA_PATH = self.ADDON.getAddonInfo('path')  # Addon folder
        self.DATA_PATH = self.ADDON.getAddonInfo('profile')  # Addon user data folder

        # Add absolute paths of embedded py modules to python system directory
        ENUMPATH = os.path.join(self.ADDON_DATA_PATH, 'modules', 'enum')
        if ENUMPATH not in sys.path:
            sys.path.insert(0, ENUMPATH)

        self.CACHE_PATH = os.path.join(self.DATA_PATH, 'cache')
        self.COOKIE_PATH = os.path.join(self.DATA_PATH, 'COOKIE')
        self.CACHE_TTL = self.ADDON.getSettingInt('cache_ttl') * 60
        self.CACHE_METADATA_TTL = (
            self.ADDON.getSettingInt('cache_metadata_ttl') * 24 * 60 * 60)

        self.URL = urlparse(argv[0])
        try:
            self.PLUGIN_HANDLE = int(argv[1])
        except IndexError:
            self.PLUGIN_HANDLE = 0
        self.BASE_URL = '{scheme}://{netloc}'.format(scheme=self.URL[0],
                                                     netloc=self.URL[1])
        self.PATH = unquote(self.URL[2][1:]).decode('utf-8')
        try:
            self.PARAM_STRING = argv[2][1:]
        except IndexError:
            self.PARAM_STRING = ''
        self.REQUEST_PARAMS = dict(parse_qsl(self.PARAM_STRING))
        self.reset_time_trace()
        self.TIME_TRACE_ENABLED = self.ADDON.getSettingBool('enable_timing')
        self.IPC_OVER_HTTP = self.ADDON.getSettingBool('enable_ipc_over_http')

        import resources.lib.database.db_local as db_local
        self.LOCAL_DB = db_local.NFLocalDatabase()
        import resources.lib.database.db_shared as db_shared
        import resources.lib.database.db_utils as db_utils
        # TODO: xml settings to specify a custom path
        #  need to study how better apply to client/service
        temp_hardcoded_path = xbmc.translatePath(os.path.join(g.DATA_PATH,
                                                              'database',
                                                              db_utils.SHARED_DB_FILENAME))
        self.SHARED_DB = db_shared.NFSharedDatabase(temp_hardcoded_path)

        try:
            os.mkdir(self.DATA_PATH)
        except OSError:
            pass

        self._init_cache()
        self.init_persistent_storage()

    def _init_cache(self):
        if not os.path.exists(
                xbmc.translatePath(self.CACHE_PATH).decode('utf-8')):
            self._init_filesystem_cache()
        # This is ugly: Pass the common module into Cache.__init__ to work
        # around circular import dependencies.
        import resources.lib.common as common
        self.CACHE = cache.Cache(common, self.CACHE_PATH, self.CACHE_TTL,
                                 self.CACHE_METADATA_TTL, self.PLUGIN_HANDLE)

    def _init_filesystem_cache(self):
        # pylint: disable=broad-except
        for bucket in cache.BUCKET_NAMES:
            if bucket != cache.CACHE_LIBRARY:
                # Library gets special location in DATA_PATH root because
                # we don't want users accidentally deleting it.
                xbmcvfs.mkdirs(
                    xbmc.translatePath(
                        os.path.join(self.CACHE_PATH, bucket)))

    def initial_addon_configuration(self):
        """
        Initial addon configuration,
        helps users to automatically configure addon parameters for proper viewing of videos
        """
        run_initial_config = self.ADDON.getSettingBool('run_init_configuration')
        if run_initial_config:
            import resources.lib.common as common
            import resources.lib.kodi.ui as ui
            self.SETTINGS_MONITOR_IGNORE = True
            system = common.get_system_platform()
            common.debug('Running initial addon configuration dialogs on system: {}'.format(system))
            if system in ['osx','ios','xbox']:
                self.ADDON.setSettingBool('enable_vp9_profiles', False)
                self.ADDON.setSettingBool('enable_hevc_profiles', True)
            elif system == 'windows':
                # Currently inputstream does not support hardware video acceleration on windows,
                # there is no guarantee that we will get 4K without video hardware acceleration,
                # so no 4K configuration
                self.ADDON.setSettingBool('enable_vp9_profiles', True)
                self.ADDON.setSettingBool('enable_hevc_profiles', False)
            elif system == 'android':
                ultrahd_capable_device = False
                premium_account = ui.ask_for_confirmation(common.get_local_string(30154),
                                                          common.get_local_string(30155))
                if premium_account:
                    ultrahd_capable_device = ui.ask_for_confirmation(common.get_local_string(30154),
                                                                     common.get_local_string(30156))
                if ultrahd_capable_device:
                    ui.show_ok_dialog(common.get_local_string(30154),
                                      common.get_local_string(30157))
                    ia_enabled = xbmc.getCondVisibility('System.HasAddon(inputstream.adaptive)')
                    if ia_enabled:
                        xbmc.executebuiltin('Addon.OpenSettings(inputstream.adaptive)')
                    else:
                        ui.show_ok_dialog(common.get_local_string(30154),
                                          common.get_local_string(30046))
                    self.ADDON.setSettingBool('enable_vp9_profiles', False)
                    self.ADDON.setSettingBool('enable_hevc_profiles', True)
                else:
                    # VP9 should have better performance since there is no need for 4k
                    self.ADDON.setSettingBool('enable_vp9_profiles', True)
                    self.ADDON.setSettingBool('enable_hevc_profiles', False)
                self.ADDON.setSettingBool('enable_force_hdcp', ultrahd_capable_device)
            elif system == 'linux':
                # Too many different linux systems, we can not predict all the behaviors
                # Some linux distributions have encountered problems with VP9,
                # OMSC users complain that hevc creates problems
                self.ADDON.setSettingBool('enable_vp9_profiles', False)
                self.ADDON.setSettingBool('enable_hevc_profiles', False)
            else:
                self.ADDON.setSettingBool('enable_vp9_profiles', False)
                self.ADDON.setSettingBool('enable_hevc_profiles', False)
            self.ADDON.setSettingBool('run_init_configuration', False)
            self.SETTINGS_MONITOR_IGNORE = False

    def init_persistent_storage(self):
        """
        Save on disk the data to keep in memory,
        at each screen change kodi reinitializes the addon
        making it impossible to have persistent variables
        """
        # This is ugly: Pass the common module into Cache.__init__ to work
        # around circular import dependencies.
        import resources.lib.common as common
        # In PersistentStorage "save on destroy" here cause problems because often gets destroyed by various behaviors
        self.PERSISTENT_STORAGE = common.PersistentStorage(__name__, no_save_on_destroy=True)
        # If missing create necessary keys
        if not self.PERSISTENT_STORAGE.get('show_menus'):
            self.PERSISTENT_STORAGE['show_menus'] = {}
        if not self.PERSISTENT_STORAGE.get('menu_sortorder'):
            self.PERSISTENT_STORAGE['menu_sortorder'] = {}
        if not self.PERSISTENT_STORAGE.get('sub_menus'):
            self.PERSISTENT_STORAGE['sub_menus'] = {}

    def library(self):
        """Get the current library instance"""
        # pylint: disable=global-statement, attribute-defined-outside-init
        if not self._library:
            try:
                self._library = self.CACHE.get(cache.CACHE_LIBRARY, 'library')
            except cache.CacheMiss:
                self._library = {}
        return self._library

    def save_library(self):
        """Save the library to disk via cache"""
        if self._library is not None:
            self.CACHE.add(cache.CACHE_LIBRARY, 'library', self._library,
                           ttl=cache.TTL_INFINITE, to_disk=True)

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
        self.ADDON.setSetting('edge_esn', edge_esn)
        return edge_esn

    def is_known_menu_context(self, context):
        """Return true if context are one of the menu with lolomo_known=True"""
        for menu_id, data in self.MAIN_MENU_ITEMS.iteritems():
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


# pylint: disable=invalid-name
# This will have no effect most of the time, as it doesn't seem to be executed
# on subsequent addon invocations when reuseLanguageInvoker is being used.
# We initialize an empty instance so the instance is importable from addon.py
# and service.py, where g.init_globals(sys.argv) MUST be called before doing
# anything else (even BEFORE OTHER IMPORTS from this addon)
g = GlobalVariables()
