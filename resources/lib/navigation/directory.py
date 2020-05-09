# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Navigation for classic plugin directory listing mode

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import xbmc
import xbmcplugin

import resources.lib.common as common
import resources.lib.kodi.library as library
import resources.lib.kodi.ui as ui
from resources.lib.database.db_utils import TABLE_MENU_DATA
from resources.lib.globals import g
from resources.lib.navigation.directory_utils import (finalize_directory, convert_list_to_dir_items, custom_viewmode,
                                                      end_of_directory, get_title, verify_profile_pin)

# What means dynamic menus (and dynamic id):
#  Are considered dynamic menus all menus which context name do not exists in the 'lolomo_contexts' of
#  MAIN_MENU_ITEMS items in globals.py.
#  These menus are generated on the fly (they are not hardcoded) and their data references are saved in TABLE_MENU_DATA
#  as menu item (with same structure of MAIN_MENU_ITEMS items in globals.py)

# The same TABLE_MENU_DATA table is used to temporary store the title of menus of the main menu which can change
# dynamically according to the language set by the profile, and it is the most practical way to get the title
# when opening a menu

# The 'pathitems':
#  It should match the 'path' key in MAIN_MENU_ITEMS of globals.py (or when not listed the dynamic menu item)
#  the indexes are: 0 the function name of DirectoryBuilder class, 1 the menu id, 2 an optional id


class Directory(object):
    """Directory listings"""

    def __init__(self, params):
        common.debug('Initializing "Directory" with params: {}', params)
        self.params = params
        # After build url the param value is converted as string
        self.perpetual_range_start = (None if self.params.get('perpetual_range_start') == 'None'
                                      else self.params.get('perpetual_range_start'))
        self.dir_update_listing = bool(self.perpetual_range_start)
        if self.perpetual_range_start == '0':
            # For cache identifier purpose
            self.perpetual_range_start = None

    def root(self, pathitems=None):  # pylint: disable=unused-argument
        """Show profiles or home listing when profile auto-selection is enabled"""
        # Get the URL parent path of the navigation: xbmc.getInfoLabel('Container.FolderPath')
        #   it can be found in Kodi log as "ParentPath = [xyz]" but not always return the exact value
        is_parent_root_path = xbmc.getInfoLabel('Container.FolderPath') == g.BASE_URL + '/'
        # Fetch initial page to refresh all session data
        if is_parent_root_path:
            common.make_call('fetch_initial_page')
        # Note when the profiles are updated to the database (by fetch_initial_page call),
        #   the update sanitize also relative settings to profiles (see _delete_non_existing_profiles in website.py)
        autoselect_profile_guid = g.LOCAL_DB.get_value('autoselect_profile_guid', '')
        if autoselect_profile_guid:
            if is_parent_root_path:
                common.info('Performing auto-selection of profile {}', autoselect_profile_guid)
            # Do not perform the profile switch if navigation come from a page that is not the root url,
            # prevents profile switching when returning to the main menu from one of the sub-menus
            if not is_parent_root_path or self._activate_profile(autoselect_profile_guid):
                self.home(None, False, True)
                return
        list_data, extra_data = common.make_call('get_profiles', {'request_update': False})
        self._profiles(list_data, extra_data)

    @custom_viewmode(g.VIEW_PROFILES)
    def profiles(self, pathitems=None):  # pylint: disable=unused-argument
        """Show profiles listing"""
        common.debug('Showing profiles listing')
        list_data, extra_data = common.make_call('get_profiles', {'request_update': True})
        self._profiles(list_data, extra_data)

    def _profiles(self, list_data, extra_data):  # pylint: disable=unused-argument
        # The standard kodi theme does not allow to change view type if the content is "files" type,
        # so here we use "images" type, visually better to see
        finalize_directory(convert_list_to_dir_items(list_data), g.CONTENT_IMAGES)
        end_of_directory(False, False)

    @common.time_execution(immediate=False)
    @custom_viewmode(g.VIEW_MAINMENU)
    def home(self, pathitems=None, cache_to_disc=True, is_autoselect_profile=False):  # pylint: disable=unused-argument
        """Show home listing"""
        if not is_autoselect_profile and 'switch_profile_guid' in self.params:
            # This is executed only when you have selected a profile from the profile list
            if not self._activate_profile(self.params['switch_profile_guid']):
                xbmcplugin.endOfDirectory(g.PLUGIN_HANDLE, succeeded=False)
                return
        common.debug('Showing home listing')
        list_data, extra_data = common.make_call('get_mainmenu')  # pylint: disable=unused-variable
        finalize_directory(convert_list_to_dir_items(list_data), g.CONTENT_FOLDER,
                           title=(g.LOCAL_DB.get_profile_config('profileName', '???') +
                                  ' - ' + common.get_local_string(30097)))
        end_of_directory(False, cache_to_disc)

    def _activate_profile(self, guid):
        pin_result = verify_profile_pin(guid)
        if not pin_result:
            if pin_result is not None:
                ui.show_notification(common.get_local_string(30106), time=8000)
            return False
        common.make_call('activate_profile', guid)
        return True

    @common.time_execution(immediate=False)
    @common.inject_video_id(path_offset=0, inject_full_pathitems=True)
    def show(self, videoid, pathitems):
        if videoid.mediatype == common.VideoId.SEASON:
            self._episodes(videoid, pathitems)
        else:
            self._seasons(videoid, pathitems)

    @custom_viewmode(g.VIEW_SEASON)
    def _seasons(self, videoid, pathitems):
        """Show the seasons list of a tv show"""
        call_args = {
            'pathitems': pathitems,
            'tvshowid_dict': videoid.to_dict(),
            'perpetual_range_start': self.perpetual_range_start,
        }
        list_data, extra_data = common.make_call('get_seasons', call_args)

        finalize_directory(convert_list_to_dir_items(list_data), g.CONTENT_SEASON, 'sort_only_label',
                           title=extra_data.get('title', ''))
        end_of_directory(self.dir_update_listing)

    @custom_viewmode(g.VIEW_EPISODE)
    def _episodes(self, videoid, pathitems):
        """Show the episodes list of a season"""
        call_args = {
            'pathitems': pathitems,
            'seasonid_dict': videoid.to_dict(),
            'perpetual_range_start': self.perpetual_range_start,
        }
        list_data, extra_data = common.make_call('get_episodes', call_args)

        finalize_directory(convert_list_to_dir_items(list_data), g.CONTENT_EPISODE, 'sort_episodes',
                           title=extra_data.get('title', ''))
        end_of_directory(self.dir_update_listing)

    @common.time_execution(immediate=False)
    @custom_viewmode(g.VIEW_SHOW)
    def video_list(self, pathitems):
        """Show a video list of a list ID"""
        menu_data = g.MAIN_MENU_ITEMS.get(pathitems[1])
        if not menu_data:  # Dynamic menus
            menu_data = g.LOCAL_DB.get_value(pathitems[1], table=TABLE_MENU_DATA, data_type=dict)
        call_args = {
            'list_id': pathitems[2],
            'menu_data': menu_data,
            'is_dynamic_id': not g.is_known_menu_context(pathitems[2])
        }
        list_data, extra_data = common.make_call('get_video_list', call_args)

        finalize_directory(convert_list_to_dir_items(list_data), menu_data.get('content_type', g.CONTENT_SHOW),
                           title=get_title(menu_data, extra_data))
        end_of_directory(False)
        return menu_data.get('view')

    @common.time_execution(immediate=False)
    @custom_viewmode(g.VIEW_SHOW)
    def video_list_sorted(self, pathitems):
        """Show a video list sorted of a 'context' name"""
        menu_data = g.MAIN_MENU_ITEMS.get(pathitems[1])
        if not menu_data:  # Dynamic menus
            menu_data = g.LOCAL_DB.get_value(pathitems[1], table=TABLE_MENU_DATA, data_type=dict)
        call_args = {
            'pathitems': pathitems,
            'menu_data': menu_data,
            'sub_genre_id': self.params.get('genre_id'),  # Used to show the sub-genre folder (when sub-genre exists)
            'perpetual_range_start': self.perpetual_range_start,
            'is_dynamic_id': not g.is_known_menu_context(pathitems[2])
        }
        list_data, extra_data = common.make_call('get_video_list_sorted', call_args)
        sort_type = 'sort_nothing'
        if menu_data['path'][1] == 'myList' and int(g.ADDON.getSettingInt('menu_sortorder_mylist')) == 0:
            # At the moment it is not possible to make a query with results sorted for the 'mylist',
            # so we adding the sort order of kodi
            sort_type = 'sort_label_ignore_folders'

        finalize_directory(convert_list_to_dir_items(list_data), menu_data.get('content_type', g.CONTENT_SHOW),
                           title=get_title(menu_data, extra_data), sort_type=sort_type)

        end_of_directory(self.dir_update_listing)
        return menu_data.get('view')

    @common.time_execution(immediate=False)
    @custom_viewmode(g.VIEW_FOLDER)
    def recommendations(self, pathitems):
        """Show video lists for a genre"""
        menu_data = g.MAIN_MENU_ITEMS.get(pathitems[1])
        call_args = {
            'menu_data': menu_data,
            'genre_id': None,
            'force_use_videolist_id': True,
        }
        list_data, extra_data = common.make_call('get_genres', call_args)

        finalize_directory(convert_list_to_dir_items(list_data), g.CONTENT_FOLDER,
                           title=get_title(menu_data, extra_data), sort_type='sort_label')
        end_of_directory(False)
        return menu_data.get('view')

    @common.time_execution(immediate=False)
    @custom_viewmode(g.VIEW_SHOW)
    def supplemental(self, pathitems):  # pylint: disable=unused-argument
        """Show supplemental video list (eg. trailers) of a tv show / movie"""
        menu_data = {'path': ['is_context_menu_item', 'is_context_menu_item'],  # Menu item do not exists
                     'title': common.get_local_string(30179)}
        from json import loads
        call_args = {
            'menu_data': menu_data,
            'video_id_dict': loads(self.params['video_id_dict']),
            'supplemental_type': self.params['supplemental_type']
        }
        list_data, extra_data = common.make_call('get_video_list_supplemental', call_args)

        finalize_directory(convert_list_to_dir_items(list_data), menu_data.get('content_type', g.CONTENT_SHOW),
                           title=get_title(menu_data, extra_data))
        end_of_directory(self.dir_update_listing)
        return menu_data.get('view')

    @common.time_execution(immediate=False)
    @custom_viewmode(g.VIEW_FOLDER)
    def genres(self, pathitems):
        """Show lolomo list of a genre or from lolomo root the list of contexts specified in the menu data"""
        menu_data = g.MAIN_MENU_ITEMS.get(pathitems[1])
        if not menu_data:  # Dynamic menus
            menu_data = g.LOCAL_DB.get_value(pathitems[1], table=TABLE_MENU_DATA, data_type=dict)
        call_args = {
            'menu_data': menu_data,
            # When genre_id is None is loaded the lolomo root the list of contexts specified in the menu data
            'genre_id': None if len(pathitems) < 3 else pathitems[2],
            'force_use_videolist_id': False,
        }
        list_data, extra_data = common.make_call('get_genres', call_args)

        finalize_directory(convert_list_to_dir_items(list_data), g.CONTENT_FOLDER,
                           title=get_title(menu_data, extra_data), sort_type='sort_label')
        end_of_directory(False)
        return menu_data.get('view')

    @custom_viewmode(g.VIEW_FOLDER)
    def subgenres(self, pathitems):
        """Show a lists of sub-genres of a 'genre id'"""
        menu_data = g.MAIN_MENU_ITEMS[pathitems[1]]
        call_args = {
            'menu_data': menu_data,
            'genre_id': pathitems[2]
        }
        list_data, extra_data = common.make_call('get_subgenres', call_args)

        finalize_directory(convert_list_to_dir_items(list_data), menu_data.get('content_type', g.CONTENT_SHOW),
                           title=get_title(menu_data, extra_data),
                           sort_type='sort_label')
        end_of_directory(False)
        return menu_data.get('view')

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
        chunked_video_list, perpetual_range_selector = library.list_contents(self.perpetual_range_start)
        if chunked_video_list:
            self._exported_directory(pathitems, chunked_video_list, perpetual_range_selector)
        else:
            ui.show_notification(common.get_local_string(30111))
            xbmcplugin.endOfDirectory(g.PLUGIN_HANDLE, succeeded=False)

    @custom_viewmode(g.VIEW_SHOW)
    def _exported_directory(self, pathitems, chunked_video_list, perpetual_range_selector):
        menu_data = g.MAIN_MENU_ITEMS['exported']
        call_args = {
            'pathitems': pathitems,
            'menu_data': menu_data,
            'chunked_video_list': chunked_video_list,
            'perpetual_range_selector': perpetual_range_selector
        }
        list_data, extra_data = common.make_call('get_video_list_chunked', call_args)

        finalize_directory(convert_list_to_dir_items(list_data), menu_data.get('content_type', g.CONTENT_SHOW),
                           title=get_title(menu_data, extra_data))
        end_of_directory(self.dir_update_listing)
        return menu_data.get('view')


def _ask_search_term_and_redirect():
    search_term = ui.ask_for_search_term()
    if search_term:
        url = common.build_url(['search', 'search', search_term], mode=g.MODE_DIRECTORY)
        xbmcplugin.endOfDirectory(g.PLUGIN_HANDLE, succeeded=True)
        xbmc.executebuiltin('Container.Update({})'.format(url))
    else:
        url = common.build_url(pathitems=['home'], mode=g.MODE_DIRECTORY)
        xbmcplugin.endOfDirectory(g.PLUGIN_HANDLE, succeeded=True)
        xbmc.executebuiltin('Container.Update({},replace)'.format(url))  # replace=reset history


def _display_search_results(pathitems, perpetual_range_start, dir_update_listing):
    menu_data = g.MAIN_MENU_ITEMS['search']
    call_args = {
        'menu_data': menu_data,
        'search_term': pathitems[2],
        'pathitems': pathitems,
        'perpetual_range_start': perpetual_range_start
    }
    list_data, extra_data = common.make_call('get_video_list_search', call_args)
    if list_data:
        _search_results_directory(pathitems, menu_data, list_data, extra_data, dir_update_listing)
    else:
        ui.show_notification(common.get_local_string(30013))
        xbmcplugin.endOfDirectory(g.PLUGIN_HANDLE, succeeded=False)


@common.time_execution(immediate=False)
@custom_viewmode(g.VIEW_SHOW)
def _search_results_directory(pathitems, menu_data, list_data, extra_data, dir_update_listing):
    extra_data['title'] = common.get_local_string(30011) + ' - ' + pathitems[2]
    finalize_directory(convert_list_to_dir_items(list_data), menu_data.get('content_type', g.CONTENT_SHOW),
                       title=get_title(menu_data, extra_data))
    end_of_directory(dir_update_listing)
    return menu_data.get('view')
