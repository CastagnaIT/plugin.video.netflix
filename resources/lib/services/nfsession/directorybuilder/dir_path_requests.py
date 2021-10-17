# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2020 Stefano Gottardo (original implementation module)
    Builds and executes PATH requests for the directories

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from typing import TYPE_CHECKING

from resources.lib import common
from resources.lib.utils.data_types import (VideoListSorted, SubgenreList, SeasonList, EpisodeList, LoCo, VideoList,
                                            SearchVideoList, CustomVideoList, LoLoMoCategory)
from resources.lib.common.exceptions import InvalidVideoListTypeError, InvalidVideoId
from resources.lib.utils.api_paths import (VIDEO_LIST_PARTIAL_PATHS, RANGE_PLACEHOLDER, VIDEO_LIST_BASIC_PARTIAL_PATHS,
                                           SEASONS_PARTIAL_PATHS, EPISODES_PARTIAL_PATHS, ART_PARTIAL_PATHS,
                                           TRAILER_PARTIAL_PATHS, PATH_REQUEST_SIZE_STD, build_paths,
                                           PATH_REQUEST_SIZE_MAX)
from resources.lib.common import cache_utils
from resources.lib.globals import G
from resources.lib.utils.logging import LOG

if TYPE_CHECKING:  # This variable/imports are used only by the editor, so not at runtime
    from resources.lib.services.nfsession.nfsession_ops import NFSessionOperations


class DirectoryPathRequests:
    """Builds and executes PATH requests for the directories"""

    def __init__(self, nfsession: 'NFSessionOperations'):
        self.nfsession = nfsession

    @cache_utils.cache_output(cache_utils.CACHE_MYLIST, fixed_identifier='my_list_items', ignore_self_class=True)
    def req_mylist_items(self):
        """Return the 'my list' video list as videoid items"""
        LOG.debug('Requesting "my list" video list as videoid items')
        try:
            items = []
            video_list = self.req_datatype_video_list_full(G.MAIN_MENU_ITEMS['myList']['request_context_name'])
            if video_list:
                # pylint: disable=unused-variable
                items = [common.VideoId.from_videolist_item(video)
                         for video_id, video in video_list.videos.items()
                         if video['queue'].get('inQueue', False)]
            return items
        except InvalidVideoListTypeError:
            return []

    @cache_utils.cache_output(cache_utils.CACHE_COMMON, fixed_identifier='loco_list', ignore_self_class=True)
    def req_loco_list_root(self):
        """Retrieve root LoCo list"""
        # It is used to following cases:
        # - To get items for the main menu
        #      (when 'loco_known'==True and loco_contexts is set, see MAIN_MENU_ITEMS in globals.py)
        # - To get list items for menus that have multiple contexts set to 'loco_contexts' like 'recommendations' menu
        LOG.debug('Requesting LoCo root lists')
        paths = ([['loco', 'componentSummary'],
                  ['loco', {'from': 0, 'to': 50}, 'componentSummary'],
                  # Titles of first 4 videos in each video list (needed only to show titles in the plot description)
                  ['loco', {'from': 0, 'to': 50}, {'from': 0, 'to': 3}, 'reference', ['title', 'summary']]] +
                 # Art for the first video of each context list (needed only to add art to the menu item)
                 build_paths(['loco', {'from': 0, 'to': 50}, 0, 'reference'], ART_PARTIAL_PATHS))
        call_args = {'paths': paths}
        path_response = self.nfsession.path_request(**call_args)
        return LoCo(path_response)

    @cache_utils.cache_output(cache_utils.CACHE_GENRES, identify_from_kwarg_name='genre_id', ignore_self_class=True)
    def req_loco_list_genre(self, genre_id):
        """Retrieve LoCo for the given genre"""
        LOG.debug('Requesting LoCo for genre {}', genre_id)
        paths = ([['genres', genre_id, 'name'],
                  ['genres', genre_id, 'rw', 'componentSummary'],
                  ['genres', genre_id, 'rw', {'from': 0, 'to': 48}, 'componentSummary'],
                  # Titles of first 4 videos in each video list (needed only to show titles in the plot description)
                  ['genres', genre_id, 'rw',
                   {'from': 0, 'to': 48}, {'from': 0, 'to': 3}, 'reference', ['title', 'summary']]] +
                 # Art for the first video of each context list (needed only to add art to the menu item)
                 build_paths(['genres', genre_id, 'rw', {'from': 0, 'to': 48}, 0, 'reference'], ART_PARTIAL_PATHS) +
                 # IDs and names of sub-genres
                 [['genres', genre_id, 'subgenres', {'from': 0, 'to': 30}, ['id', 'name']]])
        call_args = {'paths': paths}
        path_response = self.nfsession.path_request(**call_args)
        return LoCo(path_response)

    def get_loco_list_id_by_context(self, context):
        """Return the dynamic video list ID for a LoCo context"""
        try:
            return next(iter(self.req_loco_list_root().lists_by_context([context], True)))[0]
        except StopIteration as exc:
            raise InvalidVideoListTypeError(f'No lists with context {context} available') from exc

    @cache_utils.cache_output(cache_utils.CACHE_COMMON, fixed_identifier='profiles_raw_data',
                              ttl=300, ignore_self_class=True)
    def req_profiles_info(self, update_database=True):
        """Retrieve raw data of the profiles (and save it to the database)"""
        paths = ([['profilesList', 'summary'],
                  ['profilesList', 'current', 'summary'],
                  ['profilesList', {'to': 5}, 'summary'],
                  ['profilesList', {'to': 5}, 'avatar', 'images', 'byWidth', 320]])
        path_response = self.nfsession.path_request(paths, use_jsongraph=True)
        if update_database:
            from resources.lib.utils.website import parse_profiles
            parse_profiles(path_response)
        return path_response

    @cache_utils.cache_output(cache_utils.CACHE_COMMON, identify_append_from_kwarg_name='perpetual_range_start',
                              ignore_self_class=True)
    def req_seasons(self, videoid, perpetual_range_start):
        """Retrieve the seasons of a tv show"""
        if videoid.mediatype != common.VideoId.SHOW:
            raise InvalidVideoId(f'Cannot request season list for {videoid}')
        LOG.debug('Requesting the seasons list for show {}', videoid)
        call_args = {
            'paths': (build_paths(['videos', videoid.tvshowid], SEASONS_PARTIAL_PATHS) +
                      build_paths(['videos', videoid.tvshowid], ART_PARTIAL_PATHS)),
            'length_params': ['stdlist_wid', ['videos', videoid.tvshowid, 'seasonList']],
            'perpetual_range_start': perpetual_range_start
        }
        path_response = self.nfsession.perpetual_path_request(**call_args)
        return SeasonList(videoid, path_response)

    @cache_utils.cache_output(cache_utils.CACHE_COMMON, identify_from_kwarg_name='videoid',
                              identify_append_from_kwarg_name='perpetual_range_start', ignore_self_class=True)
    def req_episodes(self, videoid, perpetual_range_start=None):
        """Retrieve the episodes of a season"""
        if videoid.mediatype != common.VideoId.SEASON:
            raise InvalidVideoId(f'Cannot request episode list for {videoid}')
        LOG.debug('Requesting episode list for {}', videoid)
        paths = ([['seasons', videoid.seasonid, 'summary']] +
                 build_paths(['seasons', videoid.seasonid, 'episodes', RANGE_PLACEHOLDER], EPISODES_PARTIAL_PATHS) +
                 build_paths(['videos', videoid.tvshowid], ART_PARTIAL_PATHS + [['title']]))
        call_args = {
            'paths': paths,
            'length_params': ['stdlist_wid', ['seasons', videoid.seasonid, 'episodes']],
            'perpetual_range_start': perpetual_range_start
        }
        path_response = self.nfsession.perpetual_path_request(**call_args)
        return EpisodeList(videoid, path_response)

    @cache_utils.cache_output(cache_utils.CACHE_COMMON, identify_append_from_kwarg_name='perpetual_range_start',
                              ignore_self_class=True)
    def req_video_list(self, list_id, perpetual_range_start=None):
        """Retrieve a video list"""
        # Some of this type of request have results fixed at ~40 from netflix
        # The 'length' tag never return to the actual total count of the elements
        LOG.debug('Requesting video list {}', list_id)
        paths = build_paths(['lists', list_id, RANGE_PLACEHOLDER, 'reference'], VIDEO_LIST_PARTIAL_PATHS)
        call_args = {
            'paths': paths,
            'length_params': ['stdlist', ['lists', list_id]],
            'perpetual_range_start': perpetual_range_start
        }
        path_response = self.nfsession.perpetual_path_request(**call_args)
        return VideoList(path_response)

    @cache_utils.cache_output(cache_utils.CACHE_COMMON, identify_from_kwarg_name='context_id',
                              identify_append_from_kwarg_name='perpetual_range_start', ignore_self_class=True)
    def req_video_list_sorted(self, context_name, context_id=None, perpetual_range_start=None, menu_data=None):
        """Retrieve a video list sorted"""
        # This type of request allows to obtain more than ~40 results
        LOG.debug('Requesting video list sorted for context name: "{}", context id: "{}"',
                  context_name, context_id)
        base_path = [context_name]
        response_type = 'stdlist'
        if context_id:
            base_path.append(context_id)
            response_type = 'stdlist_wid'

        # enum order: AZ|ZA|Suggested|Year
        # sort order the "mylist" is supported only in US country, the only way to query is use 'az'
        sort_order_types = ['az', 'za', 'su', 'yr'] if not context_name == 'mylist' else ['az', 'az']
        req_sort_order_type = sort_order_types[
            int(G.ADDON.getSettingInt('menu_sortorder_' + menu_data.get('initial_menu_id', menu_data['path'][1])))
        ]
        base_path.append(req_sort_order_type)
        _base_path = list(base_path)
        _base_path.append(RANGE_PLACEHOLDER)
        if not menu_data.get('query_without_reference', False):
            _base_path.append('reference')
        paths = build_paths(_base_path, VIDEO_LIST_PARTIAL_PATHS)

        path_response = self.nfsession.perpetual_path_request(paths, [response_type, base_path], perpetual_range_start)
        return VideoListSorted(path_response, context_name, context_id, req_sort_order_type)

    @cache_utils.cache_output(cache_utils.CACHE_SUPPLEMENTAL, identify_append_from_kwarg_name='supplemental_type',
                              ignore_self_class=True)
    def req_video_list_supplemental(self, videoid, supplemental_type):
        """Retrieve a video list of supplemental type videos"""
        if videoid.mediatype not in (common.VideoId.SHOW, common.VideoId.MOVIE):
            raise InvalidVideoId(f'Cannot request video list supplemental for {videoid}')
        LOG.debug('Requesting video list supplemental of type "{}" for {}', supplemental_type, videoid)
        path = build_paths(
            ['videos', videoid.value, supplemental_type, {"from": 0, "to": 35}], TRAILER_PARTIAL_PATHS
        )
        path_response = self.nfsession.path_request(path)
        return VideoListSorted(path_response, 'videos', videoid.value, supplemental_type)

    @cache_utils.cache_output(cache_utils.CACHE_COMMON, identify_from_kwarg_name='chunked_video_list',
                              ttl=900, ignore_self_class=True)
    def req_video_list_chunked(self, chunked_video_list, perpetual_range_selector=None):
        """Retrieve a video list which contains the video ids specified"""
        if not any(isinstance(item, list) for item in chunked_video_list):
            raise InvalidVideoListTypeError('The chunked_video_list not contains a list of a list of videoids')
        merged_response = {}
        for videoids_list in chunked_video_list:
            path = build_paths(['videos', videoids_list], VIDEO_LIST_PARTIAL_PATHS)
            path_response = self.nfsession.path_request(path)
            common.merge_dicts(path_response, merged_response)

        if perpetual_range_selector:
            merged_response.update(perpetual_range_selector)
        return CustomVideoList(merged_response)

    @cache_utils.cache_output(cache_utils.CACHE_SEARCH, identify_from_kwarg_name='search_term',
                              identify_append_from_kwarg_name='perpetual_range_start', ttl=900, ignore_self_class=True)
    def req_video_list_search(self, search_term, perpetual_range_start=None):
        """Retrieve a video list by search term"""
        LOG.debug('Requesting video list by search term "{}"', search_term)
        base_path = ['search', 'byTerm', f'|{search_term}', 'titles', PATH_REQUEST_SIZE_STD]
        paths = ([base_path + [['id', 'name', 'requestId']]] +
                 build_paths(base_path + [RANGE_PLACEHOLDER, 'reference'], VIDEO_LIST_PARTIAL_PATHS))
        call_args = {
            'paths': paths,
            'length_params': ['searchlist', ['search', 'byReference']],
            'perpetual_range_start': perpetual_range_start
        }
        path_response = self.nfsession.perpetual_path_request(**call_args)
        return SearchVideoList(path_response)

    def req_subgenres(self, genre_id):
        """Retrieve sub-genres for the given genre"""
        LOG.debug('Requesting sub-genres of the genre {}', genre_id)
        path = [['genres', genre_id, 'subgenres', {'from': 0, 'to': 47}, ['id', 'name']]]
        path_response = self.nfsession.path_request(path)
        return SubgenreList(path_response)

    def req_datatype_video_list_full(self, context_name, switch_profiles=False):
        """
        Retrieve the FULL video list for a context name (no limits to the number of path requests)
        contains only minimal video info
        """
        LOG.debug('Requesting the full video list for {}', context_name)
        paths = build_paths([context_name, 'az', RANGE_PLACEHOLDER], VIDEO_LIST_BASIC_PARTIAL_PATHS)
        call_args = {
            'paths': paths,
            'length_params': ['stdlist', [context_name, 'az']],
            'perpetual_range_start': None,
            'request_size': PATH_REQUEST_SIZE_MAX,
            'no_limit_req': True
        }
        if switch_profiles:
            # Used only with library auto-update with the sync with Netflix "My List" enabled.
            # It may happen that the user browses the frontend with a different profile used by library sync,
            # and it could cause a wrong query request to nf server.
            # So we try to switch the profile, get My List items and restore previous
            # active profile in a "single call" to try perform the operations in a faster way.
            path_response = self.nfsession.perpetual_path_request_switch_profiles(**call_args)
        else:
            path_response = self.nfsession.perpetual_path_request(**call_args)
        return None if not path_response else VideoListSorted(path_response, context_name, None, 'az')

    def req_datatype_video_list_byid(self, video_ids, custom_partial_paths=None):
        """Retrieve a video list which contains the specified by video ids and return a CustomVideoList object"""
        LOG.debug('Requesting a video list for {} videos', video_ids)
        paths = build_paths(['videos', video_ids],
                            custom_partial_paths if custom_partial_paths else VIDEO_LIST_PARTIAL_PATHS)
        path_response = self.nfsession.path_request(paths)
        return CustomVideoList(path_response)

    @cache_utils.cache_output(cache_utils.CACHE_COMMON, fixed_identifier='lolomo_category',
                              identify_append_from_kwarg_name='category_name', ignore_self_class=True)
    def req_lolomo_category(self, category_name):
        """Retrieve LoLoMo by category lists"""
        LOG.debug('Requesting LoLoMo "{}" category lists', category_name)
        paths = ([['lolomoByCategory', category_name, ['componentSummary']],
                  ['lolomoByCategory', category_name, {'from': 0, 'to': 10}, ['componentSummary']],
                  # Titles of first 4 videos in each video list (needed only to show titles in the plot description)
                  ['lolomoByCategory', category_name,
                   {'from': 0, 'to': 10}, {'from': 0, 'to': 3}, 'reference', ['title', 'summary']]] +
                 # Art for the first video of each context list (needed only to add art to the menu item)
                 build_paths(['lolomoByCategory', category_name,
                              {'from': 0, 'to': 10}, 0, 'reference'], ART_PARTIAL_PATHS))
        call_args = {'paths': paths}
        path_response = self.nfsession.path_request(**call_args)
        return LoLoMoCategory(path_response)
