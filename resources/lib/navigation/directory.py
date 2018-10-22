# -*- coding: utf-8 -*-
"""Navigation for classic plugin directory listing mode"""
from __future__ import unicode_literals

import resources.lib.common as common
import resources.lib.api.shakti as api
import resources.lib.kodi.listings as listings
from resources.lib.navigation import InvalidPathError

BASE_PATH_ITEM = 'directory'

def build(pathitems, params):
    """Build a directory listing for the given path"""
    try:
        builder = DirectoryBuilder(params).__getattribute__(
            pathitems[0] if pathitems else 'root')
    except AttributeError:
        raise InvalidPathError('Cannot route {}'.format('/'.join(pathitems)))

    common.debug('Invoking directory handler {}'.format(builder.__name__))

    if len(pathitems) > 1:
        builder((pathitems[1:]))
    else:
        builder()

class DirectoryBuilder(object):
    """Builds directory listings"""
    # pylint: disable=no-self-use
    def __init__(self, params):
        common.debug('Initializing directory builder: {}'.format(params))

        profile_id = params.get('profile_id')
        if profile_id:
            api.activate_profile(profile_id)

    def root(self):
        """Show profiles or home listing is autologin es enabled"""
        autologin = common.ADDON.getSettingBool('autologin_enable')
        profile_id = common.ADDON.getSetting('autologin_id')
        if autologin and profile_id:
            common.debug('Performing auto-login for selected profile {}'
                         .format(profile_id))
            api.activate_profile(profile_id)
            self.home()
        else:
            self.profiles()

    def profiles(self):
        """Show profiles listing"""
        common.debug('Showing profiles listing')
        listings.build_profiles_listing(api.profiles())

    def home(self):
        """Show home listing"""
        common.debug('Showing root video lists')
        listings.build_main_menu_listing(
            lolomo=api.root_lists())

    def video_list(self, pathitems):
        """Show a video list"""
        # Use predefined names instead of dynamic IDs for common video lists
        if pathitems[0] in common.KNOWN_LIST_TYPES:
            list_id = api.list_id_for_type(pathitems[0])
        else:
            list_id = pathitems[0]

        listings.build_video_listing(
            video_list=api.video_list(list_id))

    def show(self, pathitems):
        """Show seasons of a tvshow"""
        tvshowid = pathitems[0]
        if len(pathitems) > 2:
            self.season(tvshowid, pathitems[2:])
        else:
            listings.build_season_listing(
                tvshowid=tvshowid,
                season_list=api.seasons(tvshowid))

    def season(self, tvshowid, pathitems):
        """Show episodes of a season"""
        seasonid = pathitems[0]
        listings.build_episode_listing(
            tvshowid=tvshowid,
            seasonid=seasonid,
            episode_list=api.episodes(tvshowid, seasonid))
