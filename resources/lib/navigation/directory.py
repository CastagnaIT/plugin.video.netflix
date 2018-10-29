# -*- coding: utf-8 -*-
"""Navigation for classic plugin directory listing mode"""
from __future__ import unicode_literals

import resources.lib.common as common
import resources.lib.api.shakti as api
import resources.lib.kodi.listings as listings

class DirectoryBuilder(object):
    """Builds directory listings"""
    # pylint: disable=no-self-use
    def __init__(self, params):
        common.debug('Initializing directory builder: {}'.format(params))
        self.params = params

        profile_id = params.get('profile_id')
        if profile_id:
            api.activate_profile(profile_id)

    def root(self, pathitems=None):
        """Show profiles or home listing is autologin es enabled"""
        # pylint: disable=unused-argument
        autologin = common.ADDON.getSettingBool('autologin_enable')
        profile_id = common.ADDON.getSetting('autologin_id')
        if autologin and profile_id:
            common.debug('Performing auto-login for selected profile {}'
                         .format(profile_id))
            api.activate_profile(profile_id)
            self.home()
        else:
            self.profiles()

    def profiles(self, pathitems=None):
        """Show profiles listing"""
        # pylint: disable=unused-argument
        common.debug('Showing profiles listing')
        listings.build_profiles_listing(api.profiles())

    def home(self, pathitems=None):
        """Show home listing"""
        # pylint: disable=unused-argument
        common.debug('Showing root video lists')
        listings.build_main_menu_listing(api.root_lists())

    def video_list(self, pathitems):
        """Show a video list"""
        # Use predefined names instead of dynamic IDs for common video lists
        if pathitems[0] in common.KNOWN_LIST_TYPES:
            list_id = api.list_id_for_type(pathitems[0])
        else:
            list_id = pathitems[0]

        listings.build_video_listing(api.video_list(list_id),
                                     self.params.get('genreId'))

    @common.inject_video_id(path_offset=0)
    def show(self, videoid):
        """Show seasons of a tvshow"""
        if videoid.mediatype == common.VideoId.SEASON:
            self.season(videoid)
        else:
            listings.build_season_listing(videoid, api.seasons(videoid))

    def season(self, videoid):
        """Show episodes of a season"""
        listings.build_episode_listing(videoid, api.episodes(videoid))

    def genres(self, pathitems=None):
        """Show video lists for a genre"""
        if not pathitems:
            lolomo = api.root_lists()
            contexts = common.MISC_CONTEXTS['genres']['contexts']
        else:
            lolomo = api.genre(pathitems[0])
            contexts = None
        listings.build_lolomo_listing(lolomo, contexts)

    def recommendations(self, pathitems=None):
        """Show video lists for a genre"""
        # pylint: disable=unused-argument
        listings.build_lolomo_listing(
            api.root_lists(),
            common.MISC_CONTEXTS['recommendations']['contexts'])
