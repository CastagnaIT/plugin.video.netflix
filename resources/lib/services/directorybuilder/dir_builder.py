# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2020 Stefano Gottardo (original implementation module)
    Prepare the data to build a directory of xbmcgui.ListItem's

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

from future.utils import iteritems

from resources.lib import common
from resources.lib.api.data_types import merge_data_type
from resources.lib.common import VideoId, g
from resources.lib.services.directorybuilder.dir_builder_items import (build_video_listing, build_subgenres_listing,
                                                                       build_season_listing, build_episode_listing,
                                                                       build_lolomo_listing, build_mainmenu_listing,
                                                                       build_profiles_listing)
from resources.lib.services.directorybuilder.dir_builder_requests import DirectoryRequests


class DirectoryBuilder(DirectoryRequests):
    """Prepare the data to build a directory"""
    def __init__(self, netflix_session):
        super(DirectoryBuilder, self).__init__()
        self.netflix_session = netflix_session
        self.slots = [
            self.get_mainmenu,
            self.get_profiles,
            self.get_seasons,
            self.get_episodes,
            self.get_video_list,
            self.get_video_list_sorted,
            self.get_video_list_supplemental,
            self.get_video_list_chunked,
            self.get_video_list_search,
            self.get_genres,
            self.get_subgenres,
            self.get_mylist_videoids_profile_switch,
            self.add_videoids_to_video_list_cache,
            self.get_continuewatching_videoid_exists
        ]
        for slot in self.slots:
            common.register_slot(slot)

    @common.time_execution(immediate=True)
    @common.addonsignals_return_call
    def get_mainmenu(self):
        lolomo_list = self.req_lolomo_list_root()
        return build_mainmenu_listing(lolomo_list)

    @common.time_execution(immediate=True)
    @common.addonsignals_return_call
    def get_profiles(self, request_update):
        """
        Get the list of profiles stored to the database
        :param request_update: when true, perform a request to the shakti API to fetch new profile data
        """
        # The profiles data are automatically updated (parsed from falcorCache) in the following situations:
        # -At first log-in, see '_login' in nf_session_access.py
        # -When navigation accesses to the root path, see 'root' in directory.py (ref. to 'fetch_initial_page' call)
        if request_update:
            self.req_profiles_info()
        return build_profiles_listing()

    @common.time_execution(immediate=True)
    @common.addonsignals_return_call
    def get_seasons(self, pathitems, tvshowid_dict, perpetual_range_start):
        tvshowid = VideoId.from_dict(tvshowid_dict)
        season_list = self.req_seasons(tvshowid, perpetual_range_start=perpetual_range_start)
        return build_season_listing(season_list, tvshowid, pathitems)

    @common.time_execution(immediate=True)
    @common.addonsignals_return_call
    def get_episodes(self, pathitems, seasonid_dict, perpetual_range_start):
        seasonid = VideoId.from_dict(seasonid_dict)
        episodes_list = self.req_episodes(seasonid, perpetual_range_start=perpetual_range_start)
        return build_episode_listing(episodes_list, seasonid, pathitems)

    @common.time_execution(immediate=True)
    @common.addonsignals_return_call
    def get_video_list(self, list_id, menu_data, is_dynamic_id):
        if not is_dynamic_id:
            list_id = self.get_lolomo_list_id_by_context(menu_data['lolomo_contexts'][0])
        return build_video_listing(self.req_video_list(list_id), menu_data, mylist_items=self.req_mylist_items())

    @common.time_execution(immediate=True)
    @common.addonsignals_return_call
    def get_video_list_sorted(self, pathitems, menu_data, sub_genre_id, perpetual_range_start, is_dynamic_id):
        context_id = None
        if is_dynamic_id and pathitems[2] != 'None':
            # Dynamic IDs for common video lists
            # The context_id can be:
            # -In the lolomo list: 'video list id'
            # -In the video list: 'sub-genre id'
            # -In the list of genres: 'sub-genre id'
            context_id = pathitems[2]
        video_list = self.req_video_list_sorted(menu_data['request_context_name'],
                                                context_id=context_id,
                                                perpetual_range_start=perpetual_range_start,
                                                menu_data=menu_data)
        return build_video_listing(video_list, menu_data, sub_genre_id, pathitems, perpetual_range_start,
                                   self.req_mylist_items())

    @common.time_execution(immediate=True)
    @common.addonsignals_return_call
    def get_video_list_supplemental(self, menu_data, video_id_dict, supplemental_type):
        video_list = self.req_video_list_supplemental(VideoId.from_dict(video_id_dict),
                                                      supplemental_type=supplemental_type)
        return build_video_listing(video_list, menu_data, mylist_items=[])

    @common.time_execution(immediate=True)
    @common.addonsignals_return_call
    def get_video_list_chunked(self, pathitems, menu_data, chunked_video_list, perpetual_range_selector):
        video_list = self.req_video_list_chunked(chunked_video_list, perpetual_range_selector=perpetual_range_selector)
        return build_video_listing(video_list, menu_data, pathitems=pathitems, mylist_items=self.req_mylist_items())

    @common.time_execution(immediate=True)
    @common.addonsignals_return_call
    def get_video_list_search(self, pathitems, menu_data, search_term, perpetual_range_start):
        video_list = self.req_video_list_search(search_term, perpetual_range_start=perpetual_range_start)
        return build_video_listing(video_list, menu_data, pathitems=pathitems, mylist_items=self.req_mylist_items())

    @common.time_execution(immediate=True)
    @common.addonsignals_return_call
    def get_genres(self, menu_data, genre_id, force_use_videolist_id):
        if genre_id:
            # Load the LoLoMo list of the specified genre
            lolomo_list = self.req_lolomo_list_genre(genre_id)
            exclude_lolomo_known = True
        else:
            # Load the LoLoMo root list filtered by 'lolomo_contexts' specified in the menu_data
            lolomo_list = self.req_lolomo_list_root()
            exclude_lolomo_known = False
        return build_lolomo_listing(lolomo_list, menu_data, force_use_videolist_id, exclude_lolomo_known)

    @common.time_execution(immediate=True)
    @common.addonsignals_return_call
    def get_subgenres(self, menu_data, genre_id):
        subgenre_list = self.req_subgenres(genre_id)
        return build_subgenres_listing(subgenre_list, menu_data)

    @common.time_execution(immediate=True)
    @common.addonsignals_return_call
    def get_mylist_videoids_profile_switch(self):
        # Special method used for library sync with my list
        video_list = self.req_datatype_video_list_full('mylist', True)
        video_id_list = [video_id for video_id, video in iteritems(video_list.videos)]
        video_id_list_type = [video['summary']['type'] for video_id, video in iteritems(video_list.videos)]
        return video_id_list, video_id_list_type

    @common.time_execution(immediate=True)
    @common.addonsignals_return_call
    def add_videoids_to_video_list_cache(self, cache_bucket, cache_identifier, video_ids):
        """Add the specified video ids to a video list datatype in the cache"""
        # Warning this method raise CacheMiss exception if cache is missing
        video_list_sorted_data = g.CACHE.get(cache_bucket, cache_identifier)
        merge_data_type(video_list_sorted_data, self.req_datatype_video_list_byid(video_ids))
        g.CACHE.add(cache_bucket, cache_identifier, video_list_sorted_data)

    @common.addonsignals_return_call
    def get_continuewatching_videoid_exists(self, video_id):
        """
        Special method used to know if a video id exists in lolomo continue watching list

        :param video_id: videoid as [string] value
        :return: a tuple ([bool] true if videoid exists, [string] the current list id, that depends from lolomo id)
        """
        list_id = self.get_lolomo_list_id_by_context('continueWatching')
        video_list = self.req_video_list(list_id).videos if video_id else []
        return video_id in video_list, list_id
