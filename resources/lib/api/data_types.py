# -*- coding: utf-8 -*-
"""Convenience representations of datatypes returned by the API"""
# pylint: disable=too-few-public-methods
from __future__ import unicode_literals

from collections import OrderedDict

from .paths import resolve_refs

class LoLoMo(object):
    """List of list of movies (lolomo)"""
    # pylint: disable=invalid-name
    def __init__(self, path_response):
        self.data = path_response
        self.id = self.data['lolomo'][1]
        self.lists = OrderedDict(
            resolve_refs(self.data['lolomos'][self.id], self.data))

    def lists_by_context(self, context):
        """Return a generator expression that iterates over all video
        lists with the given context.
        Will match any video lists with type contained in context
        if context is a list."""
        if isinstance(context, list):
            lists = ((list_id, video_list)
                     for list_id, video_list in self.lists.iteritems()
                     if video_list['context'] in context)
        else:
            lists = ((list_id, video_list)
                     for list_id, video_list in self.lists.iteritems()
                     if video_list['context'] == context)
        return lists

class VideoList(object):
    """A video list"""
    # pylint: disable=invalid-name
    def __init__(self, path_response):
        self.data = path_response
        self.id = self.data['lists'].keys()[0]
        self.videos = OrderedDict(
            resolve_refs(self.data['lists'][self.id], self.data))

class SeasonList(object):
    """A list of seasons. Includes tvshow art."""
    def __init__(self, videoid, path_response):
        self.data = path_response
        self.videoid = videoid
        self.seasons = OrderedDict(
            resolve_refs(
                self.data['videos'][self.videoid.tvshowid]['seasonList'],
                self.data))
        self.tvshow = self.data['videos'][self.videoid.tvshowid]

class EpisodeList(object):
    """A list of episodes. Includes tvshow art."""
    def __init__(self, videoid, path_response):
        self.data = path_response
        self.videoid = videoid
        self.episodes = OrderedDict(
            resolve_refs(
                self.data['seasons'][self.videoid.seasonid]['episodes'],
                self.data))
        self.tvshow = self.data['videos'][self.videoid.tvshowid]
