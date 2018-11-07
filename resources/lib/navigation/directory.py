# -*- coding: utf-8 -*-
"""Navigation for classic plugin directory listing mode"""
from __future__ import unicode_literals

import xbmc
import xbmcplugin

from resources.lib.globals import g
import resources.lib.common as common
import resources.lib.api.shakti as api
import resources.lib.kodi.listings as listings
import resources.lib.kodi.ui as ui
import resources.lib.kodi.library as library


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
        autologin = g.ADDON.getSettingBool('autologin_enable')
        profile_id = g.ADDON.getSetting('autologin_id')
        if autologin and profile_id:
            common.debug('Performing auto-login for selected profile {}'
                         .format(profile_id))
            api.activate_profile(profile_id)
            self.home()
        else:
            self.profiles()

    @common.time_execution
    def profiles(self, pathitems=None):
        """Show profiles listing"""
        # pylint: disable=unused-argument
        common.debug('Showing profiles listing')
        listings.build_profiles_listing(api.profiles())

    @common.time_execution
    def home(self, pathitems=None):
        """Show home listing"""
        # pylint: disable=unused-argument
        common.debug('Showing root video lists')
        listings.build_main_menu_listing(api.root_lists())

    @common.time_execution
    def video_list(self, pathitems):
        """Show a video list"""
        # Use predefined names instead of dynamic IDs for common video lists
        if pathitems[1] in g.KNOWN_LIST_TYPES:
            list_id = api.list_id_for_type(pathitems[1])
        else:
            list_id = pathitems[1]

        listings.build_video_listing(api.video_list(list_id))

    @common.inject_video_id(path_offset=0)
    @common.time_execution
    def show(self, videoid):
        """Show seasons of a tvshow"""
        if videoid.mediatype == common.VideoId.SEASON:
            self.season(videoid)
        else:
            listings.build_season_listing(videoid, api.seasons(videoid))

    def season(self, videoid):
        """Show episodes of a season"""
        listings.build_episode_listing(videoid, api.episodes(videoid))

    @common.time_execution
    def genres(self, pathitems):
        """Show video lists for a genre"""
        if len(pathitems) < 2:
            lolomo = api.root_lists()
            contexts = g.MISC_CONTEXTS['genres']['contexts']
        else:
            lolomo = api.genre(pathitems[1])
            contexts = None
        listings.build_lolomo_listing(lolomo, contexts)

    @common.time_execution
    def recommendations(self, pathitems=None):
        """Show video lists for a genre"""
        # pylint: disable=unused-argument
        listings.build_lolomo_listing(
            api.root_lists(),
            g.MISC_CONTEXTS['recommendations']['contexts'])

    def search(self, pathitems):
        """Ask for a search term if none is given via path, query API
        and display search results"""
        if len(pathitems) == 1:
            _ask_search_term_and_redirect()
        else:
            _display_search_results(pathitems[1])

    @common.time_execution
    def exported(self, pathitems=None):
        """List all items that are exported to the Kodi library"""
        # pylint: disable=unused-argument
        library_contents = library.list_contents()
        if library_contents:
            listings.build_video_listing(
                api.custom_video_list(library_contents))
        else:
            ui.show_notification(common.get_local_string(30013))
            xbmcplugin.endOfDirectory(g.PLUGIN_HANDLE, succeeded=False)


def _ask_search_term_and_redirect():
    search_term = ui.ask_for_search_term()
    if search_term:
        url = common.build_url(['search', search_term], mode=g.MODE_DIRECTORY)
        xbmcplugin.endOfDirectory(g.PLUGIN_HANDLE, succeeded=True)
        xbmc.executebuiltin('Container.Update({},replace)'.format(url))
    else:
        xbmcplugin.endOfDirectory(g.PLUGIN_HANDLE, succeeded=False)


@common.time_execution
def _display_search_results(search_term):
    search_results = api.search(search_term)
    if search_results.videos:
        listings.build_video_listing(search_results)
        return
    else:
        ui.show_notification(common.get_local_string(30013))
        xbmcplugin.endOfDirectory(g.PLUGIN_HANDLE, succeeded=False)
