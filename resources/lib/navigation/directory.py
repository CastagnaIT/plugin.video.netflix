# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Navigation for classic plugin directory listing mode

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import xbmcplugin

import resources.lib.common as common
import resources.lib.kodi.library_utils as lib_utils
import resources.lib.kodi.ui as ui
from resources.lib.database.db_utils import TABLE_MENU_DATA
from resources.lib.globals import G
from resources.lib.navigation.directory_utils import (finalize_directory, custom_viewmode,
                                                      end_of_directory, get_title, activate_profile, auto_scroll)
from resources.lib.utils.logging import LOG, measure_exec_time_decorator


# What means dynamic menus (and dynamic id):
#  Are considered dynamic menus all menus which context name do not exists in the 'loco_contexts' of
#  MAIN_MENU_ITEMS items in globals.py.
#  These menus are generated on the fly (they are not hardcoded) and their data references are saved in TABLE_MENU_DATA
#  as menu item (with same structure of MAIN_MENU_ITEMS items in globals.py)

# The same TABLE_MENU_DATA table is used to temporary store the title of menus of the main menu which can change
# dynamically according to the language set by the profile, and it is the most practical way to get the title
# when opening a menu

# The 'pathitems':
#  It should match the 'path' key in MAIN_MENU_ITEMS of globals.py (or when not listed the dynamic menu item)
#  the indexes are: 0 the function name of this 'Directory' class, 1 the menu id, 2 an optional id


class Directory:
    """Directory listings"""

    def __init__(self, params):
        LOG.debug('Initializing "Directory" with params: {}', params)
        self.params = params
        # After build url the param value is converted as string
        self.perpetual_range_start = (None if self.params.get('perpetual_range_start') == 'None'
                                      else self.params.get('perpetual_range_start'))
        if 'dir_update_listing' in self.params:
            self.dir_update_listing = self.params['dir_update_listing'] == 'True'
        else:
            self.dir_update_listing = bool(self.perpetual_range_start)
        if self.perpetual_range_start == '0':
            # For cache identifier purpose
            self.perpetual_range_start = None

    def root(self, pathitems=None):  # pylint: disable=unused-argument
        """Show profiles or home listing when profile auto-selection is enabled"""
        # Fetch initial page to refresh all session data
        current_directory = common.WndHomeProps[common.WndHomeProps.CURRENT_DIRECTORY]
        if not current_directory:
            # Note when the profiles are updated to the database (by fetch_initial_page call),
            # the update sanitize also relative settings to profiles (see _delete_non_existing_profiles in website.py)
            common.make_call('fetch_initial_page')
        # When the add-on is used in a browser window, we do not have to execute the auto profile selection
        if not G.IS_ADDON_EXTERNAL_CALL:
            autoselect_profile_guid = G.LOCAL_DB.get_value('autoselect_profile_guid', '')
            if autoselect_profile_guid and not common.WndHomeProps[common.WndHomeProps.IS_CONTAINER_REFRESHED]:
                if not current_directory:
                    LOG.info('Performing auto-selection of profile {}', autoselect_profile_guid)
                    self.params['switch_profile_guid'] = autoselect_profile_guid
                self.home(None)
                return
        dir_items, extra_data = common.make_call('get_profiles', {'request_update': False})
        self._profiles(dir_items, extra_data)

    def profiles(self, pathitems=None):  # pylint: disable=unused-argument
        """Show profiles listing"""
        LOG.debug('Showing profiles listing')
        dir_items, extra_data = common.make_call('get_profiles', {'request_update': True})
        self._profiles(dir_items, extra_data)

    @custom_viewmode(G.VIEW_PROFILES)
    def _profiles(self, dir_items, extra_data):  # pylint: disable=unused-argument
        # The standard kodi theme does not allow to change view type if the content is "files" type,
        # so here we use "images" type, visually better to see
        finalize_directory(dir_items, G.CONTENT_IMAGES)
        end_of_directory(True)

    @measure_exec_time_decorator()
    @custom_viewmode(G.VIEW_MAINMENU)
    def home(self, pathitems=None):  # pylint: disable=unused-argument
        """Show home listing"""
        if 'switch_profile_guid' in self.params:
            if G.IS_ADDON_EXTERNAL_CALL:
                # Profile switch/ask PIN only once
                ret = not self.params['switch_profile_guid'] == G.LOCAL_DB.get_active_profile_guid()
            else:
                # Profile switch/ask PIN every time you come from ...
                ret = common.WndHomeProps[common.WndHomeProps.CURRENT_DIRECTORY] in ['', 'root', 'profiles']
            if ret and not activate_profile(self.params['switch_profile_guid']):
                xbmcplugin.endOfDirectory(G.PLUGIN_HANDLE, succeeded=False)
                return
        LOG.debug('Showing home listing')
        dir_items, extra_data = common.make_call('get_mainmenu')  # pylint: disable=unused-variable
        finalize_directory(dir_items, G.CONTENT_FOLDER,
                           title=(G.LOCAL_DB.get_profile_config('profileName', '???') +
                                  ' - ' + common.get_local_string(30097)))
        end_of_directory(True)

    @measure_exec_time_decorator()
    @common.inject_video_id(path_offset=0, inject_full_pathitems=True)
    def show(self, videoid, pathitems):
        if videoid.mediatype == common.VideoId.SEASON:
            self._episodes(videoid, pathitems)
        else:
            self._seasons(videoid, pathitems)

    def _seasons(self, videoid, pathitems):
        """Show the seasons list of a tv show"""
        call_args = {
            'pathitems': pathitems,
            'tvshowid_dict': videoid.to_dict(),
            'perpetual_range_start': self.perpetual_range_start,
        }
        dir_items, extra_data = common.make_call('get_seasons', call_args)
        if len(dir_items) == 1:
            # If there is only one season, load and show the episodes now
            pathitems = dir_items[0][0].replace(G.BASE_URL, '').strip('/').split('/')[1:]
            videoid = common.VideoId.from_path(pathitems)
            self._episodes(videoid, pathitems)
            return
        self._seasons_directory(dir_items, extra_data)

    @custom_viewmode(G.VIEW_SEASON)
    def _seasons_directory(self, dir_items, extra_data):
        finalize_directory(dir_items, G.CONTENT_SEASON, 'sort_only_label',
                           title=extra_data.get('title', ''))
        end_of_directory(self.dir_update_listing)

    @custom_viewmode(G.VIEW_EPISODE)
    def _episodes(self, videoid, pathitems):
        """Show the episodes list of a season"""
        call_args = {
            'pathitems': pathitems,
            'seasonid_dict': videoid.to_dict(),
            'perpetual_range_start': self.perpetual_range_start,
        }
        dir_items, extra_data = common.make_call('get_episodes', call_args)
        finalize_directory(dir_items, G.CONTENT_EPISODE, 'sort_episodes',
                           title=extra_data.get('title', ''))
        end_of_directory(self.dir_update_listing)
        auto_scroll(dir_items)

    @measure_exec_time_decorator()
    @custom_viewmode(G.VIEW_SHOW)
    def video_list(self, pathitems):
        """Show a video list of a list ID"""
        menu_data = G.MAIN_MENU_ITEMS.get(pathitems[1])
        if not menu_data:  # Dynamic menus
            menu_data = G.LOCAL_DB.get_value(pathitems[1], table=TABLE_MENU_DATA, data_type=dict)
        call_args = {
            'list_id': pathitems[2],
            'menu_data': menu_data,
            'is_dynamic_id': not G.is_known_menu_context(pathitems[2])
        }
        dir_items, extra_data = common.make_call('get_video_list', call_args)

        finalize_directory(dir_items, menu_data.get('content_type', G.CONTENT_SHOW),
                           title=get_title(menu_data, extra_data))
        end_of_directory(False)
        return menu_data.get('view')

    @measure_exec_time_decorator()
    @custom_viewmode(G.VIEW_SHOW)
    def video_list_sorted(self, pathitems):
        """Show a video list sorted of a 'context' name"""
        menu_data = G.MAIN_MENU_ITEMS.get(pathitems[1])
        if not menu_data:  # Dynamic menus
            menu_data = G.LOCAL_DB.get_value(pathitems[1], table=TABLE_MENU_DATA, data_type=dict)
        call_args = {
            'pathitems': pathitems,
            'menu_data': menu_data,
            'sub_genre_id': self.params.get('sub_genre_id'),  # Used to show the sub-genre folder when sub-genres exists
            'perpetual_range_start': self.perpetual_range_start,
            'is_dynamic_id': not G.is_known_menu_context(pathitems[2])
        }
        dir_items, extra_data = common.make_call('get_video_list_sorted', call_args)
        sort_type = 'sort_nothing'
        if menu_data['path'][1] == 'myList' and int(G.ADDON.getSettingInt('menu_sortorder_mylist')) == 0:
            # At the moment it is not possible to make a query with results sorted for the 'mylist',
            # so we adding the sort order of kodi
            sort_type = 'sort_label_ignore_folders'

        finalize_directory(dir_items, menu_data.get('content_type', G.CONTENT_SHOW),
                           title=get_title(menu_data, extra_data), sort_type=sort_type)
        end_of_directory(self.dir_update_listing)
        return menu_data.get('view')

    @measure_exec_time_decorator()
    @custom_viewmode(G.VIEW_FOLDER)
    def category_list(self, pathitems):
        """Show a list of folders of a LoLoMo category"""
        menu_data = G.MAIN_MENU_ITEMS.get(pathitems[1])
        call_args = {
            'menu_data': menu_data
        }
        dir_items, extra_data = common.make_call('get_category_list', call_args)

        finalize_directory(dir_items, menu_data.get('content_type', G.CONTENT_FOLDER),
                           title=get_title(menu_data, extra_data), sort_type='sort_label')
        end_of_directory(self.dir_update_listing)
        return menu_data.get('view')

    @measure_exec_time_decorator()
    @custom_viewmode(G.VIEW_FOLDER)
    def recommendations(self, pathitems):
        """Show video lists for a genre"""
        menu_data = G.MAIN_MENU_ITEMS.get(pathitems[1])
        call_args = {
            'menu_data': menu_data,
            'genre_id': None,
            'force_use_videolist_id': True,
        }
        dir_items, extra_data = common.make_call('get_genres', call_args)

        finalize_directory(dir_items, G.CONTENT_FOLDER,
                           title=get_title(menu_data, extra_data), sort_type='sort_label')
        end_of_directory(False)
        return menu_data.get('view')

    @measure_exec_time_decorator()
    @custom_viewmode(G.VIEW_SHOW)
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
        dir_items, extra_data = common.make_call('get_video_list_supplemental', call_args)

        finalize_directory(dir_items, menu_data.get('content_type', G.CONTENT_SHOW),
                           title=get_title(menu_data, extra_data))
        end_of_directory(self.dir_update_listing)
        return menu_data.get('view')

    @measure_exec_time_decorator()
    @custom_viewmode(G.VIEW_FOLDER)
    def genres(self, pathitems):
        """Show loco list of a genre or from loco root the list of contexts specified in the menu data"""
        menu_data = G.MAIN_MENU_ITEMS.get(pathitems[1])
        if not menu_data:  # Dynamic menus
            menu_data = G.LOCAL_DB.get_value(pathitems[1], table=TABLE_MENU_DATA, data_type=dict)
        call_args = {
            'menu_data': menu_data,
            # When genre_id is None is loaded the loco root the list of contexts specified in the menu data
            'genre_id': None if len(pathitems) < 3 else int(pathitems[2]),
            'force_use_videolist_id': False,
        }
        dir_items, extra_data = common.make_call('get_genres', call_args)

        finalize_directory(dir_items, G.CONTENT_FOLDER,
                           title=get_title(menu_data, extra_data), sort_type='sort_label')
        end_of_directory(False)
        return menu_data.get('view')

    @custom_viewmode(G.VIEW_FOLDER)
    def subgenres(self, pathitems):
        """Show a lists of sub-genres of a 'genre id'"""
        menu_data = G.MAIN_MENU_ITEMS[pathitems[1]]
        call_args = {
            'menu_data': menu_data,
            'genre_id': pathitems[2]
        }
        dir_items, extra_data = common.make_call('get_subgenres', call_args)

        finalize_directory(dir_items, menu_data.get('content_type', G.CONTENT_SHOW),
                           title=get_title(menu_data, extra_data),
                           sort_type='sort_label')
        end_of_directory(False)
        return menu_data.get('view')

    def search(self, pathitems):
        from resources.lib.navigation.directory_search import route_search_nav
        route_search_nav(pathitems, self.perpetual_range_start, self.dir_update_listing, self.params)

    @measure_exec_time_decorator()
    def exported(self, pathitems=None):
        """List all items that are exported to the Kodi library"""
        chunked_video_list, perpetual_range_selector = lib_utils.list_contents(self.perpetual_range_start)
        if chunked_video_list:
            self._exported_directory(pathitems, chunked_video_list, perpetual_range_selector)
        else:
            ui.show_notification(common.get_local_string(30111))
            xbmcplugin.endOfDirectory(G.PLUGIN_HANDLE, succeeded=False)

    @custom_viewmode(G.VIEW_SHOW)
    def _exported_directory(self, pathitems, chunked_video_list, perpetual_range_selector):
        menu_data = G.MAIN_MENU_ITEMS['exported']
        call_args = {
            'pathitems': pathitems,
            'menu_data': menu_data,
            'chunked_video_list': chunked_video_list,
            'perpetual_range_selector': perpetual_range_selector
        }
        dir_items, extra_data = common.make_call('get_video_list_chunked', call_args)

        finalize_directory(dir_items, menu_data.get('content_type', G.CONTENT_SHOW),
                           title=get_title(menu_data, extra_data))
        end_of_directory(self.dir_update_listing)
        return menu_data.get('view')
