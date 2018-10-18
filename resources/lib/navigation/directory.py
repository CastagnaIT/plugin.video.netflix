# -*- coding: utf-8 -*-
"""Navigation for classic plugin directory listing mode"""
from __future__ import unicode_literals

import resources.lib.common as common
import resources.lib.api.shakti as api
from resources.lib.navigation import InvalidPathError

from resources.lib.kodi.KodiHelper import KodiHelper
from resources.lib.library.Library import Library

BASE_PATH_ITEM = 'directory'

def build(pathitems, params):
    """Build a directory listing for the given path"""
    try:
        builder = DirectoryBuilder(params).__getattribute__(
            pathitems[0] if pathitems else 'root')
    except AttributeError:
        raise InvalidPathError('Cannot route {}'.format('/'.join(pathitems)))

    if len(pathitems) > 1:
        builder((pathitems[1:]))
    else:
        builder()

class DirectoryBuilder(object):
    """Builds directory listings"""
    # pylint: disable=no-self-use
    def __init__(self, params):
        self.library = Library()
        self.kodi_helper = KodiHelper(library=self.library)
        self.library.kodi_helper = self.kodi_helper

        profile_id = params.get('profile_id')
        if profile_id:
            api.activate_profile(profile_id)

    def root(self):
        autologin = common.ADDON.getSettingBool('autologin_enable')
        profile_id = common.ADDON.getSetting('autologin_id')
        if autologin and profile_id:
            api.activate_profile(profile_id)
            self.home()
        else:
            self.profiles()

    def profiles(self):
        self.kodi_helper.build_profiles_listing(api.profiles())

    def home(self):
        self.kodi_helper.build_main_menu_listing(
            lolomo=api.root_lists())

    def video_list(self, pathitems):
        # Use predefined names instead of dynamic IDs for common video lists
        if pathitems[0] in common.KNOWN_LIST_TYPES:
            video_list_id = api.video_list_id_for_type(pathitems[0])
        else:
            video_list_id = pathitems[0]

        self.kodi_helper.build_video_listing(
            video_list=api.video_list(video_list_id))

    def show(self, pathitems):
        tvshowid = pathitems[0]
        if len(pathitems > 2):
            self.season(tvshowid, pathitems[2:])
        else:
            self.kodi_helper.build_season_listing(
                tvshowid=tvshowid,
                seasons=api.seasons(tvshowid))

    def season(self, tvshowid, pathitems):
        seasonid = pathitems[0]
        self.kodi_helper.build_episode_listing(
            tvshowid=tvshowid,
            seasonid=seasonid,
            episodes=api.episodes(tvshowid, seasonid))
