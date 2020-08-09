# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Convenience representations of data types returned by the API

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
# pylint: disable=too-few-public-methods
from __future__ import absolute_import, division, unicode_literals
from collections import OrderedDict
from future.utils import iteritems, itervalues, listvalues

import resources.lib.common as common

from .api_paths import resolve_refs
from .logging import LOG


class LoCo(object):
    """List of components (LoCo)"""
    def __init__(self, path_response):
        self.data = path_response
        LOG.debug('LoCo data: {}', self.data)
        _filterout_loco_contexts(self.data, ['billboard'])
        self.id = next(iter(self.data['locos']))  # Get loco root id

    def __getitem__(self, key):
        return _check_sentinel(self.data['locos'][self.id][key])

    def get(self, key, default=None):
        """Pass call on to the backing dict of this LoLoMo."""
        return self.data['locos'][self.id].get(key, default)

    def lists_by_context(self, contexts, break_on_first=False):
        """
        Get all video lists of the given contexts

        :param contexts: list of context names
        :param break_on_first: stop the research at first match
        :return iteritems of a dict where key=list id, value=VideoListLoCo object data
        """
        lists = {}
        for list_id, list_data in iteritems(self.data['lists']):
            if list_data['componentSummary']['context'] in contexts:
                lists.update({list_id: VideoListLoCo(self.data, list_id)})
                if break_on_first:
                    break
        return iteritems(lists)

    def find_by_context(self, context):
        """Return the video list and the id list of a context"""
        for list_id, data in iteritems(self.data['lists']):
            if data['componentSummary']['context'] != context:
                continue
            return list_id, VideoListLoCo(self.data, list_id)
        return None, None


class VideoListLoCo:
    """A video list, for LoCo data"""
    def __init__(self, path_response, list_id):
        # LOG.debug('VideoListLoCo data: {}', path_response)
        self.perpetual_range_selector = path_response.get('_perpetual_range_selector')
        self.data = path_response
        self.list_id = list_id
        self.videoids = None
        # Set a 'UNSPECIFIED' type videoid (special handling for menus see parse_info in infolabels.py)
        self.videoid = common.VideoId(videoid=list_id)
        self.contained_titles = None
        self.artitem = None
        if 'lists' not in path_response:
            # No data in path response
            return
        # Set videos data for the specified list id
        self.videos = OrderedDict(resolve_refs(self.data['lists'][list_id], self.data))
        if not self.videos:
            return
        # Set first videos titles (special handling for menus see parse_info in infolabels.py)
        self.contained_titles = _get_titles(self.videos)
        # Set art data of first video (special handling for menus see parse_info in infolabels.py)
        self.artitem = listvalues(self.videos)[0]
        try:
            self.videoids = _get_videoids(self.videos)
        except KeyError:
            self.videoids = None

    def __getitem__(self, key):
        return _check_sentinel(self.data['lists'][self.list_id]['componentSummary'][key])

    def get(self, key, default=None):
        """Pass call on to the backing dict of this VideoList."""
        return _check_sentinel(self.data['lists'][self.list_id]['componentSummary'].get(key, default))


class VideoList:
    """A video list"""
    def __init__(self, path_response, list_id=None):
        # LOG.debug('VideoList data: {}', path_response)
        self.perpetual_range_selector = path_response.get('_perpetual_range_selector')
        self.data = path_response
        has_data = bool(path_response.get('lists'))
        self.videos = OrderedDict()
        self.artitem = None
        self.contained_titles = None
        self.videoids = None
        if has_data:
            # Generate one videoid, or from the first id of the list or with specified one
            self.videoid = common.VideoId(
                videoid=(list_id
                         if list_id
                         else next(iter(self.data['lists']))))
            self.videos = OrderedDict(resolve_refs(self.data['lists'][self.videoid.value], self.data))
            if self.videos:
                # self.artitem = next(itervalues(self.videos))
                self.artitem = listvalues(self.videos)[0]
                self.contained_titles = _get_titles(self.videos)
                try:
                    self.videoids = _get_videoids(self.videos)
                except KeyError:
                    self.videoids = None

    def __getitem__(self, key):
        return _check_sentinel(self.data['lists'][self.videoid.value][key])

    def get(self, key, default=None):
        """Pass call on to the backing dict of this VideoList."""
        return _check_sentinel(self.data['lists'][self.videoid.value].get(key, default))


class VideoListSorted:
    """A video list"""
    def __init__(self, path_response, context_name, context_id, req_sort_order_type):
        # LOG.debug('VideoListSorted data: {}', path_response)
        self.perpetual_range_selector = path_response.get('_perpetual_range_selector')
        self.data = path_response
        self.context_name = context_name
        has_data = bool((context_id and path_response.get(context_name)
                         and path_response[context_name].get(context_id))
                        or (not context_id and path_response.get(context_name)))
        self.data_lists = {}
        self.videos = OrderedDict()
        self.artitem = None
        self.contained_titles = None
        self.videoids = None
        if has_data:
            self.data_lists = path_response[context_name][context_id][req_sort_order_type] \
                if context_id else path_response[context_name][req_sort_order_type]
            self.videos = OrderedDict(resolve_refs(self.data_lists, self.data))
            if self.videos:
                # self.artitem = next(itervalues(self.videos))
                self.artitem = listvalues(self.videos)[0]
                self.contained_titles = _get_titles(self.videos)
                try:
                    self.videoids = _get_videoids(self.videos)
                except KeyError:
                    self.videoids = None

    def __getitem__(self, key):
        return _check_sentinel(self.data_lists[key])

    def get(self, key, default=None):
        """Pass call on to the backing dict of this VideoList."""
        return _check_sentinel(self.data_lists.get(key, default))


class SearchVideoList:
    """A video list with search results"""
    def __init__(self, path_response):
        self.perpetual_range_selector = path_response.get('_perpetual_range_selector')
        self.data = path_response
        has_data = 'search' in path_response
        self.videos = OrderedDict()
        self.videoids = None
        self.artitem = None
        self.contained_titles = None
        if has_data:
            self.title = common.get_local_string(30100).format(list(self.data['search']['byTerm'])[0][1:])
            self.videos = OrderedDict(resolve_refs(list(self.data['search']['byReference'].values())[0], self.data))
            self.videoids = _get_videoids(self.videos)
            # self.artitem = next(itervalues(self.videos), None)
            self.artitem = listvalues(self.videos)[0] if self.videos else None
            self.contained_titles = _get_titles(self.videos)

    def __getitem__(self, key):
        return _check_sentinel(self.data['search'][key])

    def get(self, key, default=None):
        """Pass call on to the backing dict of this VideoList."""
        return _check_sentinel(self.data['search'].get(key, default))


class CustomVideoList:
    """A video list"""
    def __init__(self, path_response):
        self.perpetual_range_selector = path_response.get('_perpetual_range_selector')
        self.data = path_response
        self.videos = OrderedDict(self.data.get('videos', {}))
        self.videoids = _get_videoids(self.videos)
        # self.artitem = next(itervalues(self.videos))
        self.artitem = listvalues(self.videos)[0] if self.videos else None
        self.contained_titles = _get_titles(self.videos)

    def __getitem__(self, key):
        return _check_sentinel(self.data[key])

    def get(self, key, default=None):
        """Pass call on to the backing dict of this VideoList."""
        return _check_sentinel(self.data.get(key, default))


class SeasonList:
    """A list of seasons. Includes tvshow art."""
    def __init__(self, videoid, path_response):
        # LOG.debug('SeasonList data: {}', path_response)
        self.perpetual_range_selector = path_response.get('_perpetual_range_selector')
        self.data = path_response
        self.videoid = videoid
        self.tvshow = self.data['videos'][self.videoid.tvshowid]
        self.seasons = OrderedDict(
            resolve_refs(self.tvshow['seasonList'], self.data))


class EpisodeList:
    """A list of episodes. Includes tvshow art."""
    def __init__(self, videoid, path_response):
        # LOG.debug('EpisodeList data: {}', path_response)
        self.perpetual_range_selector = path_response.get('_perpetual_range_selector')
        self.data = path_response
        self.videoid = videoid
        self.tvshow = self.data['videos'][self.videoid.tvshowid]
        self.season = self.data['seasons'][self.videoid.seasonid]
        self.episodes = OrderedDict(
            resolve_refs(self.season['episodes'], self.data))


class SubgenreList:
    """A list of subgenre."""
    def __init__(self, path_response):
        # LOG.debug('Subgenre data: {}', path_response)
        self.lists = []
        if path_response:
            self.perpetual_range_selector = path_response.get('_perpetual_range_selector')
            genre_id = next(iter(path_response.get('genres', {})))
            self.subgenre_data = path_response['genres'].get(genre_id, {}).get('subgenres')
            self.lists = list(path_response['genres'].get(genre_id, {}).get('subgenres').items())


def merge_data_type(data, data_to_merge):
    for video_id, video in iteritems(data_to_merge.videos):
        data.videos[video_id] = video
    data.videoids.extend(data_to_merge.videoids)
    data.contained_titles.extend(data_to_merge.contained_titles)


def _check_sentinel(value):
    return (None
            if isinstance(value, dict) and value.get('$type') == 'sentinel'
            else value)


def _get_title(video):
    """Get the title of a video (either from direct key or nested within summary)"""
    return video.get('title', video.get('summary', {}).get('title'))


def _get_titles(videos):
    """Return a list of videos' titles"""
    return [_get_title(video)
            for video in itervalues(videos)
            if _get_title(video)]


def _get_videoids(videos):
    """Return a list of VideoId s for the videos"""
    return [common.VideoId.from_videolist_item(video)
            for video in itervalues(videos)]


def _filterout_loco_contexts(data, contexts):
    """Deletes from the data all records related to the specified contexts"""
    root_id = next(iter(data['locos']))
    for index in range(len(data['locos'][root_id]) - 1, -1, -1):
        list_id = data['locos'][root_id][str(index)][1]
        if not data['lists'][list_id]['componentSummary'].get('context') in contexts:
            continue
        del data['lists'][list_id]
        del data['locos'][root_id][str(index)]
