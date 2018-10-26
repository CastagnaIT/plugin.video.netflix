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
        self.id = (lolomoid
                   if lolomoid
                   else next(self.data['lolomos'].iterkeys()))
        self.lists = OrderedDict(
            (key, VideoList(self.data, key))
            for key, _
            in resolve_refs(self.data['lolomos'][self.id], self.data))

    def __getitem__(self, key):
        return self.data['lolomos'][self.id][key]

    def get(self, key, default=None):
        """Pass call on to the backing dict of this LoLoMo."""
        return self.data['lolomos'][self.id].get(key, default)

    def lists_by_context(self, context):
        """Return a generator expression that iterates over all video
        lists with the given context.
        Will match any video lists with type contained in context
        if context is a list."""
        match_context = ((lambda context, contexts: context in contexts)
                         if isinstance(context, list)
                         else (lambda context, target: context == target))
        return ((list_id, VideoList(self.data, list_id))
                for list_id, video_list in self.lists.iteritems()
                if match_context(video_list['context'], context))

class VideoList(object):
    """A video list"""
    # pylint: disable=invalid-name
    def __init__(self, path_response, list_id=None):
        self.data = path_response
        self.id = common.VideoId(
            videoid=(list_id
                     if list_id
                     else next(self.data['lists'].iterkeys())))
        self.videos = OrderedDict(
            resolve_refs(self.data['lists'][self.id.value], self.data))
        self.artitem = next(self.videos.itervalues())
        self.contained_titles = [video['title']
                                 for video in self.videos.itervalues()]

    def __getitem__(self, key):
        return self.data['lists'][self.id.value][key]

    def get(self, key, default=None):
        """Pass call on to the backing dict of this VideoList."""
        return _check_sentinel(self.data['lists'][self.id.value]
                               .get(key, default))

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
