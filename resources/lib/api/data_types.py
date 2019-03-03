# -*- coding: utf-8 -*-
"""Convenience representations of datatypes returned by the API"""
# pylint: disable=too-few-public-methods
from __future__ import unicode_literals

from collections import OrderedDict

import resources.lib.common as common

from .paths import resolve_refs


class LoLoMo(object):
    """List of list of movies (lolomo)"""
    # pylint: disable=invalid-name
    def __init__(self, path_response, lolomoid=None):
        self.data = path_response
        common.debug('LoLoMo data: ' + str(self.data))
        self.id = (lolomoid
                   if lolomoid
                   else next(self.data['lolomos'].iterkeys()))
        self.lists = OrderedDict(
            (key, VideoList(self.data, key))
            for key, _
            in resolve_refs(self.data['lolomos'][self.id], self.data))

    def __getitem__(self, key):
        return _check_sentinel(self.data['lolomos'][self.id][key])

    def get(self, key, default=None):
        """Pass call on to the backing dict of this LoLoMo."""
        return self.data['lolomos'][self.id].get(key, default)

    def lists_by_context(self, context, break_on_first=False):
        """Return a generator expression that iterates over all video
        lists with the given context.
        Will match any video lists with type contained in context
        if context is a list."""
        # 'context' may contain a list of multiple contexts or a single
        # 'context' can be passed as a string, convert to simplify code
        if not isinstance(context, list):
            context = [context]

        match_context = ((lambda context, contexts: context in contexts)
                         if isinstance(context, list)
                         else (lambda context, target: context == target))

        # Keep sort order of context list
        lists = {}
        for context_name in context:
            for list_id, video_list in self.lists.iteritems():
                if match_context(video_list['context'], context_name):
                    lists.update({list_id: VideoList(self.data, list_id)})
                    if break_on_first:
                        break
        return iter(lists.iteritems())


class VideoList(object):
    """A video list"""
    # pylint: disable=invalid-name
    def __init__(self, path_response, list_id=None):
        self.data = path_response
        self.id = common.VideoId(
            videoid=(list_id
                     if list_id
                     else next(self.data['lists'].iterkeys())))
        #self.title = self['displayName']   Not more used
        self.videos = OrderedDict(
            resolve_refs(self.data['lists'][self.id.value], self.data))
        if self.videos:
            self.artitem = next(self.videos.itervalues())
            self.contained_titles = _get_titles(self.videos)
            try:
                self.videoids = _get_videoids(self.videos)
            except KeyError:
                self.videoids = None
        else:
            self.artitem = None
            self.contained_titles = None
            self.videoids = None

    def __getitem__(self, key):
        return _check_sentinel(self.data['lists'][self.id.value][key])

    def get(self, key, default=None):
        """Pass call on to the backing dict of this VideoList."""
        return _check_sentinel(self.data['lists'][self.id.value]
                               .get(key, default))

class VideoListAZ(object):
    """A video list"""
    # pylint: disable=invalid-name
    def __init__(self, path_response, context_name, context_id=None):
        self.data = path_response
        self.data_lists = path_response[context_name][context_id]['az'] \
            if context_id else path_response[context_name]['az']
        self.context_name = context_name
        #self.title = self['displayName']   Not more used
        self.videos = OrderedDict(
            resolve_refs(self.data_lists, self.data))
        if self.videos:
            self.artitem = next(self.videos.itervalues())
            self.contained_titles = _get_titles(self.videos)
            try:
                self.videoids = _get_videoids(self.videos)
            except KeyError:
                self.videoids = None
        else:
            self.artitem = None
            self.contained_titles = None
            self.videoids = None

    def __getitem__(self, key):
        return _check_sentinel(self.data_lists[key])

    def get(self, key, default=None):
        """Pass call on to the backing dict of this VideoList."""
        return _check_sentinel(self.data_lists
                               .get(key, default))

class SearchVideoList(object):
    """A video list with search results"""
    # pylint: disable=invalid-name
    def __init__(self, path_response):
        self.data = path_response
        self.title = common.get_local_string(30100).format(
            self.data['search']['byTerm'].keys()[0][1:])
        self.videos = OrderedDict(
            resolve_refs(self.data['search']['byReference'].values()[0],
                         self.data))
        self.videoids = _get_videoids(self.videos)
        self.artitem = next(self.videos.itervalues(), None)
        self.contained_titles = _get_titles(self.videos)

    def __getitem__(self, key):
        return _check_sentinel(self.data['search'][key])

    def get(self, key, default=None):
        """Pass call on to the backing dict of this VideoList."""
        return _check_sentinel(self.data['search'].get(key, default))


class CustomVideoList(object):
    """A video list"""
    # pylint: disable=invalid-name
    def __init__(self, path_response):
        self.data = path_response
        self.title = common.get_local_string(30048)
        self.videos = self.data['videos']
        self.videoids = _get_videoids(self.videos)
        self.artitem = next(self.videos.itervalues())
        self.contained_titles = _get_titles(self.videos)

    def __getitem__(self, key):
        return _check_sentinel(self.data[key])

    def get(self, key, default=None):
        """Pass call on to the backing dict of this VideoList."""
        return _check_sentinel(self.data.get(key, default))


class SeasonList(object):
    """A list of seasons. Includes tvshow art."""
    def __init__(self, videoid, path_response):
        self.data = path_response
        self.videoid = videoid
        self.tvshow = self.data['videos'][self.videoid.tvshowid]
        self.seasons = OrderedDict(
            resolve_refs(self.tvshow['seasonList'], self.data))


class EpisodeList(object):
    """A list of episodes. Includes tvshow art."""
    def __init__(self, videoid, path_response):
        self.data = path_response
        self.videoid = videoid
        self.tvshow = self.data['videos'][self.videoid.tvshowid]
        self.season = self.data['seasons'][self.videoid.seasonid]
        self.episodes = OrderedDict(
            resolve_refs(self.season['episodes'], self.data))


def _check_sentinel(value):
    return (None
            if isinstance(value, dict) and value.get('$type') == 'sentinel'
            else value)


def _get_title(video):
    """Get the title of a video (either from direct key or nested within
    summary)"""
    return video.get('title', video.get('summary', {}).get('title'))


def _get_titles(videos):
    """Return a list of videos' titles"""
    return [_get_title(video)
            for video in videos.itervalues()
            if _get_title(video)]


def _get_videoids(videos):
    """Return a list of VideoId objects for the videos"""
    return [common.VideoId.from_videolist_item(video)
            for video in videos.itervalues()]
