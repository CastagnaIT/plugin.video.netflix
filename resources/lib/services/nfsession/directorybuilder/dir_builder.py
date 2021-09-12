# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2020 Stefano Gottardo (original implementation module)
    Prepare the data to build a directory of xbmcgui.ListItem's

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from resources.lib.utils.data_types import merge_data_type
from resources.lib.common.exceptions import CacheMiss
from resources.lib.common import VideoId
from resources.lib.globals import G
from resources.lib.services.nfsession.directorybuilder.dir_builder_items \
    import (build_video_listing, build_subgenres_listing, build_season_listing, build_episode_listing,
            build_loco_listing, build_mainmenu_listing, build_profiles_listing, build_lolomo_category_listing)
from resources.lib.services.nfsession.directorybuilder.dir_path_requests import DirectoryPathRequests
from resources.lib.utils.logging import measure_exec_time_decorator


class DirectoryBuilder(DirectoryPathRequests):
    """Prepare the data to build a directory"""

    def __init__(self, nfsession):
        super().__init__(nfsession)
        # Slot allocation for IPC
        self.slots = [
            self.get_mainmenu,
            self.get_profiles,
            self.get_seasons,
            self.get_episodes,
            self.get_video_list,
            self.get_video_list_sorted,
            self.get_video_list_sorted_sp,
            self.get_category_list,
            self.get_video_list_supplemental,
            self.get_video_list_chunked,
            self.get_video_list_search,
            self.get_genres,
            self.get_subgenres,
            self.get_mylist_videoids_profile_switch,
            self.add_videoids_to_video_list_cache,
            self.get_continuewatching_videoid_exists
        ]

    @measure_exec_time_decorator(is_immediate=True)
    def get_mainmenu(self):
        loco_list = self.req_loco_list_root()
        return build_mainmenu_listing(loco_list)

    @measure_exec_time_decorator(is_immediate=True)
    def get_profiles(self, request_update, preselect_guid=None, detailed_info=True):
        """
        Get the list of profiles stored to the database
        :param request_update: when true, perform a request to the shakti API to fetch new profile data
        :param preselect_guid: if set the specified profile will be highlighted, else the current active profile
        """
        # The profiles data are automatically updated (parsed from falcorCache) in the following situations:
        # -At first log-in, see '_login' in nf_session_access.py
        # -When navigation accesses to the root path, see 'root' in directory.py (ref. to 'fetch_initial_page' call)
        if request_update:
            self.req_profiles_info()
        return build_profiles_listing(preselect_guid, detailed_info)

    @measure_exec_time_decorator(is_immediate=True)
    def get_seasons(self, pathitems, tvshowid_dict, perpetual_range_start):
        tvshowid = VideoId.from_dict(tvshowid_dict)
        season_list = self.req_seasons(tvshowid, perpetual_range_start=perpetual_range_start)
        return build_season_listing(season_list, tvshowid, pathitems)

    @measure_exec_time_decorator(is_immediate=True)
    def get_episodes(self, pathitems, seasonid_dict, perpetual_range_start):
        seasonid = VideoId.from_dict(seasonid_dict)
        episodes_list = self.req_episodes(seasonid, perpetual_range_start=perpetual_range_start)
        return build_episode_listing(episodes_list, seasonid, pathitems)

    @measure_exec_time_decorator(is_immediate=True)
    def get_video_list(self, list_id, menu_data, is_dynamic_id):
        if not is_dynamic_id:
            list_id = self.get_loco_list_id_by_context(menu_data['loco_contexts'][0])
        # pylint: disable=unexpected-keyword-arg
        video_list = self.req_video_list(list_id, no_use_cache=menu_data.get('no_use_cache'))
        return build_video_listing(video_list, menu_data,
                                   mylist_items=self.req_mylist_items())

    @measure_exec_time_decorator(is_immediate=True)
    def get_video_list_sorted(self, pathitems, menu_data, sub_genre_id, perpetual_range_start, is_dynamic_id):
        context_id = None
        if is_dynamic_id and pathitems[2] != 'None':
            # Dynamic IDs for common video lists
            # The context_id can be:
            # -In the loco list: 'video list id'
            # -In the video list: 'sub-genre id'
            # -In the list of genres: 'sub-genre id'
            context_id = pathitems[2]
        # pylint: disable=unexpected-keyword-arg
        video_list = self.req_video_list_sorted(menu_data['request_context_name'],
                                                context_id=context_id,
                                                perpetual_range_start=perpetual_range_start,
                                                menu_data=menu_data,
                                                no_use_cache=menu_data.get('no_use_cache'))
        return build_video_listing(video_list, menu_data, sub_genre_id, pathitems, perpetual_range_start,
                                   self.req_mylist_items())

    @measure_exec_time_decorator(is_immediate=True)
    def get_video_list_sorted_sp(self, pathitems, menu_data, context_name, context_id, perpetual_range_start):
        # Method used for the menu search
        video_list = self.req_video_list_sorted(context_name,
                                                context_id=context_id,
                                                perpetual_range_start=perpetual_range_start,
                                                menu_data=menu_data)
        return build_video_listing(video_list, menu_data, None, pathitems, perpetual_range_start,
                                   self.req_mylist_items())

    @measure_exec_time_decorator(is_immediate=True)
    def get_category_list(self, menu_data):
        lolomo_category_list = self.req_lolomo_category(menu_data['loco_contexts'][0])
        return build_lolomo_category_listing(lolomo_category_list, menu_data)

    @measure_exec_time_decorator(is_immediate=True)
    def get_video_list_supplemental(self, menu_data, video_id_dict, supplemental_type):
        video_list = self.req_video_list_supplemental(VideoId.from_dict(video_id_dict),
                                                      supplemental_type=supplemental_type)
        return build_video_listing(video_list, menu_data, mylist_items=[])

    @measure_exec_time_decorator(is_immediate=True)
    def get_video_list_chunked(self, pathitems, menu_data, chunked_video_list, perpetual_range_selector):
        video_list = self.req_video_list_chunked(chunked_video_list, perpetual_range_selector=perpetual_range_selector)
        return build_video_listing(video_list, menu_data, pathitems=pathitems, mylist_items=self.req_mylist_items())

    @measure_exec_time_decorator(is_immediate=True)
    def get_video_list_search(self, pathitems, menu_data, search_term, perpetual_range_start, path_params=None):
        video_list = self.req_video_list_search(search_term, perpetual_range_start=perpetual_range_start)
        return build_video_listing(video_list, menu_data,
                                   pathitems=pathitems, mylist_items=self.req_mylist_items(), path_params=path_params)

    @measure_exec_time_decorator(is_immediate=True)
    def get_genres(self, menu_data, genre_id, force_use_videolist_id):
        if genre_id:
            # Load the LoCo list of the specified genre
            loco_list = self.req_loco_list_genre(genre_id)
            exclude_loco_known = True
        else:
            # Load the LoCo root list filtered by 'loco_contexts' specified in the menu_data
            loco_list = self.req_loco_list_root()
            exclude_loco_known = False
        return build_loco_listing(loco_list, menu_data, force_use_videolist_id, exclude_loco_known)

    @measure_exec_time_decorator(is_immediate=True)
    def get_subgenres(self, menu_data, genre_id):
        subgenre_list = self.req_subgenres(genre_id)
        return build_subgenres_listing(subgenre_list, menu_data)

    @measure_exec_time_decorator(is_immediate=True)
    def get_mylist_videoids_profile_switch(self):
        # Special method used for library sync with my list
        video_list = self.req_datatype_video_list_full('mylist', True)
        video_id_list = []
        video_id_list_type = []
        if video_list:
            for video_id, video in video_list.videos.items():
                video_id_list.append(video_id)
                video_id_list_type.append(video['summary']['type'])
        return video_id_list, video_id_list_type

    @measure_exec_time_decorator(is_immediate=True)
    def add_videoids_to_video_list_cache(self, cache_bucket, cache_identifier, video_ids):
        """Add the specified video ids to a video list datatype in the cache (only if the cache item exists)"""
        try:
            video_list_sorted_data = G.CACHE.get(cache_bucket, cache_identifier)
            merge_data_type(video_list_sorted_data, self.req_datatype_video_list_byid(video_ids))
            G.CACHE.add(cache_bucket, cache_identifier, video_list_sorted_data)
        except CacheMiss:
            pass

    def get_continuewatching_videoid_exists(self, video_id):
        """
        Special method used to know if a video id exists in loco continue watching list

        :param video_id: videoid as [string] value
        :return: a tuple ([bool] true if videoid exists, [string] the current list id, that depends from loco id)
        """
        list_id = self.get_loco_list_id_by_context('continueWatching')
        video_list = self.req_video_list(list_id).videos if video_id else []
        return video_id in video_list, list_id
