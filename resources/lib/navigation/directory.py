# -*- coding: utf-8 -*-
"""Navigation for classic plugin directory listing mode"""
from __future__ import unicode_literals

import xbmc
import xbmcplugin

from resources.lib.database.db_utils import (TABLE_MENU_DATA)
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
        # After build url the param value is converted as string
        self.perpetual_range_start = None \
            if self.params.get('perpetual_range_start') == 'None' else self.params.get('perpetual_range_start')
        self.dir_update_listing = True if self.perpetual_range_start else False
        if self.perpetual_range_start == '0':
            # For cache identifier purpose
            self.perpetual_range_start = None
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
            self.home(None, False)
        else:
            self.profiles()

    def profiles(self, pathitems=None):
        """Show profiles listing"""
        # pylint: disable=unused-argument
        common.debug('Showing profiles listing')
        listings.build_profiles_listing()
        _handle_endofdirectory(False, False)

    @common.time_execution(immediate=False)
    def home(self, pathitems=None, cache_to_disc=True):
        """Show home listing"""
        # pylint: disable=unused-argument
        common.debug('Showing root video lists')
        listings.build_main_menu_listing(api.root_lists())
        _handle_endofdirectory(False, cache_to_disc)

    @common.time_execution(immediate=False)
    def video_list(self, pathitems):
        """Show a video list with a listid request"""
        menu_data = g.MAIN_MENU_ITEMS.get(pathitems[1])
        if not menu_data:
            menu_data = g.LOCAL_DB.get_value(pathitems[1], table=TABLE_MENU_DATA, data_type=dict)
        if g.is_known_menu_context(pathitems[2]):
            list_id = api.list_id_for_type(menu_data['lolomo_contexts'][0])
            listings.build_video_listing(api.video_list(list_id), menu_data)
        else:
            # Dynamic IDs from generated sub-menu
            list_id = pathitems[2]
            listings.build_video_listing(api.video_list(list_id), menu_data)
        _handle_endofdirectory(False)

    @common.time_execution(immediate=False)
    def video_list_sorted(self, pathitems):
        """Show a video list with a sorted request"""
        menu_data = g.MAIN_MENU_ITEMS.get(pathitems[1])
        if not menu_data:
            menu_data = g.LOCAL_DB.get_value(pathitems[1], table=TABLE_MENU_DATA, data_type=dict)
        mainmenu_data = menu_data.copy()
        # If the menu is a sub-menu, we get the parameters of the main menu
        if menu_data.get('main_menu'):
            mainmenu_data = menu_data['main_menu']
        if menu_data.get('request_context_name', None) and g.is_known_menu_context(pathitems[2]):
            listings.build_video_listing(
                api.video_list_sorted(context_name=menu_data['request_context_name'],
                                      perpetual_range_start=self.perpetual_range_start,
                                      menu_data=mainmenu_data),
                menu_data, pathitems)
        else:
            # Dynamic IDs for common video lists
            list_id = None if pathitems[2] == 'None' else pathitems[2]
            listings.build_video_listing(
                api.video_list_sorted(context_name=menu_data['request_context_name'],
                                      context_id=list_id,
                                      perpetual_range_start=self.perpetual_range_start,
                                      menu_data=mainmenu_data),
                menu_data, pathitems, self.params.get('genre_id'))
        _handle_endofdirectory(self.dir_update_listing)

    @common.inject_video_id(path_offset=0, inject_full_pathitems=True)
    @common.time_execution(immediate=False)
    def show(self, videoid, pathitems):
        """Show seasons of a tvshow"""
        if videoid.mediatype == common.VideoId.SEASON:
            self.season(videoid, pathitems)
        else:
            listings.build_season_listing(videoid, api.seasons(videoid), pathitems)
            _handle_endofdirectory(self.dir_update_listing)

    def season(self, videoid, pathitems):
        """Show episodes of a season"""
        listings.build_episode_listing(videoid, api.episodes(videoid), pathitems)
        _handle_endofdirectory(self.dir_update_listing)

    @common.time_execution(immediate=False)
    def genres(self, pathitems):
        """Show video lists for a genre"""
        menu_data = g.MAIN_MENU_ITEMS.get(pathitems[1])
        if not menu_data:
            menu_data = g.LOCAL_DB.get_value(pathitems[1], table=TABLE_MENU_DATA, data_type=dict)
        # pathitems indexes: 0 function name, 1 menu id, 2 optional id
        if len(pathitems) < 3:
            lolomo = api.root_lists()
            listings.build_lolomo_listing(lolomo, menu_data)
        else:
            # Here is provided the id of the genre, eg. get sub-menus of tvshows (all tv show)
            lolomo = api.genre(pathitems[2])
            listings.build_lolomo_listing(lolomo, menu_data, exclude_lolomo_known=True)
        _handle_endofdirectory(False)

    def subgenres(self, pathitems):
        """Show a lists of subgenres"""
        # pathitems indexes: 0 function name, 1 menu id, 2 genre id
        menu_data = g.MAIN_MENU_ITEMS[pathitems[1]]
        listings.build_subgenre_listing(api.subgenre(pathitems[2]), menu_data)
        _handle_endofdirectory(False)

    @common.time_execution(immediate=False)
    def recommendations(self, pathitems=None):
        """Show video lists for a genre"""
        # pylint: disable=unused-argument
        listings.build_lolomo_listing(
            api.root_lists(),
            g.MAIN_MENU_ITEMS['recommendations'], force_videolistbyid=True)
        _handle_endofdirectory(False)

    def search(self, pathitems):
        """Ask for a search term if none is given via path, query API
        and display search results"""
        if len(pathitems) == 2:
            _ask_search_term_and_redirect()
        else:
            _display_search_results(pathitems, self.perpetual_range_start, self.dir_update_listing)

    @common.time_execution(immediate=False)
    def exported(self, pathitems=None):
        """List all items that are exported to the Kodi library"""
        # pylint: disable=unused-argument
        library_contents = library.list_contents()
        if library_contents:
            listings.build_video_listing(api.custom_video_list(library_contents), g.MAIN_MENU_ITEMS['exported'])
            _handle_endofdirectory(self.dir_update_listing)
        else:
            ui.show_notification(common.get_local_string(30013))
            xbmcplugin.endOfDirectory(g.PLUGIN_HANDLE, succeeded=False)

    @common.time_execution(immediate=False)
    def supplemental(self, pathitems):
        """Show supplemental videos (eg. trailers) of a tvshow/movie"""
        # pathitems indexes: 0 function name, 1 videoid value, 2 videoid mediatype, 3 supplemental_type
        videoid = common.VideoId.from_path([pathitems[2], pathitems[1]])
        listings.build_supplemental_listing(api.supplemental_video_list(videoid, pathitems[3]),
                                            pathitems)
        _handle_endofdirectory(self.dir_update_listing)


def _ask_search_term_and_redirect():
    search_term = ui.ask_for_search_term()
    if search_term:
        url = common.build_url(['search', 'search', search_term], mode=g.MODE_DIRECTORY)
        xbmcplugin.endOfDirectory(g.PLUGIN_HANDLE, succeeded=True)
        xbmc.executebuiltin('Container.Update({})'.format(url))
    else:
        xbmcplugin.endOfDirectory(g.PLUGIN_HANDLE, succeeded=False)


@common.time_execution(immediate=False)
def _display_search_results(pathitems, perpetual_range_start, dir_update_listing):
    search_term = pathitems[2]
    search_results = api.search(search_term, perpetual_range_start)
    if search_results.videos:
        listings.build_video_listing(search_results, g.MAIN_MENU_ITEMS['search'], pathitems)
        _handle_endofdirectory(dir_update_listing)
    else:
        ui.show_notification(common.get_local_string(30013))
        xbmcplugin.endOfDirectory(g.PLUGIN_HANDLE, succeeded=False)


def _handle_endofdirectory(dir_update_listing, cache_to_disc=True):
    # If dir_update_listing=True overwrite the history list, so we can get back to the main page
    xbmcplugin.endOfDirectory(g.PLUGIN_HANDLE,
                              succeeded=True,
                              updateListing=dir_update_listing,
                              cacheToDisc=cache_to_disc)
