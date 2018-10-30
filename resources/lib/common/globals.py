# -*- coding: utf-8 -*-
"""Global addon constants"""
from __future__ import unicode_literals

import sys
import os
from urlparse import urlparse, parse_qsl

import xbmc
import xbmcaddon

# Global vars are initialized in init_globals
# Commonly used addon attributes from Kodi
ADDON = None
ADDON_ID = None
PLUGIN = None
VERSION = None
DEFAULT_FANART = None
ICON = None
DATA_PATH = None
COOKIE_PATH = None
CACHE_TTL = None
CACHE_METADATA_TTL = None

# Information about the current plugin instance
URL = None
PLUGIN_HANDLE = None
BASE_URL = None
PATH = None
PARAM_STRING = None
REQUEST_PARAMS = None

KNOWN_LIST_TYPES = ['queue', 'topTen', 'netflixOriginals', 'continueWatching',
                    'trendingNow', 'newRelease', 'popularTitles']
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


def init_globals(argv):
    """Initialized globally used module variables.
    Needs to be called at start of each plugin instance!
    This is an ugly hack because Kodi doesn't execute statements defined on
    module level if reusing a language invoker."""
    # pylint: disable=global-statement
    global ADDON, ADDON_ID, PLUGIN, VERSION, DEFAULT_FANART, ICON, DATA_PATH, \
           COOKIE_PATH, CACHE_TTL, CACHE_METADATA_TTL
    ADDON = xbmcaddon.Addon()
    ADDON_ID = ADDON.getAddonInfo('id')
    PLUGIN = ADDON.getAddonInfo('name')
    VERSION = ADDON.getAddonInfo('version')
    DEFAULT_FANART = ADDON.getAddonInfo('fanart')
    ICON = ADDON.getAddonInfo('icon')
    DATA_PATH = xbmc.translatePath(ADDON.getAddonInfo('profile'))
    COOKIE_PATH = DATA_PATH + 'COOKIE'
    CACHE_TTL = ADDON.getSettingInt('cache_ttl') * 60
    CACHE_METADATA_TTL = ADDON.getSettingInt('cache_metadata_ttl') * 60

    global URL, PLUGIN_HANDLE, BASE_URL, PATH, PARAM_STRING, REQUEST_PARAMS
    URL = urlparse(argv[0])
    try:
        PLUGIN_HANDLE = int(argv[1])
    except IndexError:
        PLUGIN_HANDLE = 0
    BASE_URL = '{scheme}://{netloc}'.format(scheme=URL[0], netloc=URL[1])
    PATH = URL[2][1:]
    try:
        PARAM_STRING = argv[2][1:]
    except IndexError:
        PARAM_STRING = ''
    REQUEST_PARAMS = dict(parse_qsl(PARAM_STRING))

    try:
        os.mkdir(DATA_PATH)
    except OSError:
        pass


init_globals(sys.argv)


def get_esn():
    """Get the ESN from settings"""
    return ADDON.getSetting('esn')


def set_esn(esn):
    """
    Set the ESN in settings if it hasn't been set yet.
    Return True if the new ESN has been set, False otherwise
    """
    if not get_esn() and esn:
        ADDON.setSetting('esn', esn)
        return True
    return False


def flush_settings():
    """Reload the ADDON"""
    # pylint: disable=global-statement
    global ADDON
    ADDON = xbmcaddon.Addon()
