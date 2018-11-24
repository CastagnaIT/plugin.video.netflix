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
from urlparse import urlparse, parse_qsl
from urllib import unquote

import xbmc
import xbmcaddon
import xbmcvfs

import resources.lib.cache as cache


class GlobalVariables(object):
    """Encapsulation for global variables to work around quirks with
    Kodi's reuseLanguageInvoker behavior"""
    # pylint: disable=attribute-defined-outside-init
    # pylint: disable=invalid-name, too-many-instance-attributes
    KNOWN_LIST_TYPES = ['queue', 'topTen', 'netflixOriginals',
                        'continueWatching', 'trendingNow', 'newRelease',
                        'popularTitles']
    MISC_CONTEXTS = {
        'genres': {'label_id': 30010,
                   'description_id': 30093,
                   'icon': 'DefaultGenre.png',
                   'contexts': 'genre'},
        'recommendations': {'label_id': 30001,
                            'description_id': 30094,
                            'icon': 'DefaultUser.png',
                            'contexts': ['similars', 'becauseYouAdded']}
    }

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
        self.COOKIES = {}
        self.ADDON = xbmcaddon.Addon()
        self.ADDON_ID = self.ADDON.getAddonInfo('id')
        self.PLUGIN = self.ADDON.getAddonInfo('name')
        self.VERSION = self.ADDON.getAddonInfo('version')
        self.DEFAULT_FANART = self.ADDON.getAddonInfo('fanart')
        self.ICON = self.ADDON.getAddonInfo('icon')
        self.DATA_PATH = self.ADDON.getAddonInfo('profile')
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

        try:
            os.mkdir(self.DATA_PATH)
        except OSError:
            pass

        self._init_cache()

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

    def get_esn(self):
        """Get the ESN from settings"""
        return self.ADDON.getSetting('esn')

    def set_esn(self, esn):
        """
        Set the ESN in settings if it hasn't been set yet.
        Return True if the new ESN has been set, False otherwise
        """
        if not self.get_esn() and esn:
            self.ADDON.setSetting('esn', esn)
            return True
        return False

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
