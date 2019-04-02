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

    def profiles(self, pathitems=None):
        """Show profiles listing"""
        # pylint: disable=unused-argument
        common.debug('Showing profiles listing')
        listings.build_profiles_listing(api.profiles())

    @common.time_execution(immediate=False)
    def home(self, pathitems=None):
        """Show home listing"""
        # pylint: disable=unused-argument
        common.debug('Showing root video lists')
        listings.build_main_menu_listing(api.root_lists())

    @common.time_execution(immediate=False)
    def video_list(self, pathitems):
        """Show a video list with a listid request"""
        menu_data = g.MAIN_MENU_ITEMS.get(pathitems[1])
        if not menu_data:
            menu_data = g.PERSISTENT_STORAGE['sub_menus'][pathitems[1]]
        if g.is_known_menu_context(pathitems[2]):
            list_id = api.list_id_for_type(menu_data['lolomo_contexts'][0])
            listings.build_video_listing(api.video_list(list_id), menu_data)
        else:
            # Dynamic IDs from generated sub-menu
            list_id = pathitems[2]
            listings.build_video_listing(api.video_list(list_id), menu_data)

    @common.time_execution(immediate=False)
    def video_list_sorted(self, pathitems):
        """Show a video list with a sorted request"""
        menu_data = g.MAIN_MENU_ITEMS.get(pathitems[1])
        if not menu_data:
            menu_data = g.PERSISTENT_STORAGE['sub_menus'][pathitems[1]]
        if menu_data.get('request_context_name',None) and g.is_known_menu_context(pathitems[2]):
            listings.build_video_listing(
                api.video_list_sorted(menu_data['request_context_name'], **self.params),
                menu_data, pathitems)
        else:
            #Dynamic IDs for common video lists
            list_id = pathitems[2]
            listings.build_video_listing(
                api.video_list_sorted(menu_data['request_context_name'], list_id, **self.params),
                menu_data, pathitems)

    @common.inject_video_id(path_offset=0)
    @common.time_execution(immediate=False)
    def show(self, videoid):
        """Show seasons of a tvshow"""
        if videoid.mediatype == common.VideoId.SEASON:
            self.season(videoid)
        else:
            listings.build_season_listing(videoid, api.seasons(videoid))

    def season(self, videoid):
        """Show episodes of a season"""
        listings.build_episode_listing(videoid, api.episodes(videoid))

    @common.time_execution(immediate=False)
    def genres(self, pathitems):
        """Show video lists for a genre"""
        menu_data = g.MAIN_MENU_ITEMS[pathitems[1]]
        # pathitems indexes: 0 function name, 1 menu id, 2 optional id
        if len(pathitems) < 3:
            lolomo = api.root_lists()
            listings.build_lolomo_listing(lolomo, menu_data)
        else:
            #Here is provided the id of the genre, eg. get sub-menus of tvshows (all tv show)
            lolomo = api.genre(pathitems[2])
            listings.build_lolomo_listing(lolomo, menu_data, exclude_lolomo_known=True)

    @common.time_execution(immediate=False)
    def recommendations(self, pathitems=None):
        """Show video lists for a genre"""
        # pylint: disable=unused-argument
        listings.build_lolomo_listing(
            api.root_lists(),
            g.MAIN_MENU_ITEMS['recommendations'], force_videolistbyid=True)

    def search(self, pathitems):
        """Ask for a search term if none is given via path, query API
        and display search results"""
        if len(pathitems) == 2:
            _ask_search_term_and_redirect()
        else:
            _display_search_results(pathitems[2], **self.params)

    @common.time_execution(immediate=False)
    def exported(self, pathitems=None):
        """List all items that are exported to the Kodi library"""
        # pylint: disable=unused-argument
        library_contents = library.list_contents()
        if library_contents:
            listings.build_video_listing(
                api.custom_video_list(library_contents), g.MAIN_MENU_ITEMS['exported'])
        else:
            ui.show_notification(common.get_local_string(30013))
            xbmcplugin.endOfDirectory(g.PLUGIN_HANDLE, succeeded=False)


def _ask_search_term_and_redirect():
    search_term = ui.ask_for_search_term()
    if search_term:
        url = common.build_url(['search', 'search', search_term],
                               mode=g.MODE_DIRECTORY)
        xbmcplugin.endOfDirectory(g.PLUGIN_HANDLE, succeeded=True)
        xbmc.executebuiltin('Container.Update({},replace)'
                            .format(url))
    else:
        xbmcplugin.endOfDirectory(g.PLUGIN_HANDLE, succeeded=False)


@common.time_execution(immediate=False)
def _display_search_results(search_term, **kwargs):
    search_results = api.search(search_term, **kwargs)
    if search_results.videos:
        listings.build_video_listing(search_results, g.MAIN_MENU_ITEMS['search'],
                                     ['search', 'search', search_term])
    else:
        ui.show_notification(common.get_local_string(30013))
        xbmcplugin.endOfDirectory(g.PLUGIN_HANDLE, succeeded=False)
