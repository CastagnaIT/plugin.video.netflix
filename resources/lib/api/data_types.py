# -*- coding: utf-8 -*-
"""Convenience representations of datatypes returned by the API"""
# pylint: disable=too-few-public-methods
from __future__ import unicode_literals

from collections import OrderedDict

import resources.lib.common as common

from .paths import ART_PARTIAL_PATHS

class LoLoMo(object):
    """List of list of movies (lolomo)"""
    # pylint: disable=invalid-name
    def __init__(self, path_response):
        self.data = path_response
        self.id = self.data['lolomo'][1]
        self.lists = OrderedDict(
            _sort_and_resolve_refs(self.data['lolomos'][self.id],
                                   self.data))

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
            _sort_and_resolve_refs(self.data['lists'][self.id],
                                   self.data))

class SeasonList(object):
    """A video list"""
    # pylint: disable=invalid-name
    def __init__(self, tvshowid, path_response):
        self.data = path_response
        self.tvshowid = tvshowid
        self.seasons = OrderedDict(
            _sort_and_resolve_refs(
                self.data['videos'][self.tvshowid]['seasonList'], self.data))
        self.tvshow = self.data['videos'][self.tvshowid]

class EpisodeList(object):
    """A video list"""
    # pylint: disable=invalid-name
    def __init__(self, tvshowid, seasonid, path_response):
        self.data = path_response
        self.tvshowid = tvshowid
        self.seasonid = seasonid
        self.episodes = OrderedDict(
            _sort_and_resolve_refs(
                self.data['seasons'][self.seasonid]['episodes'], self.data))
        self.tvshowart = None

class InvalidReferenceError(Exception):
    """The provided reference cannot be dealt with as it is in an
    unexpected format"""
    pass

def _sort_and_resolve_refs(references, targets):
    """Return a generator expression that returns the objects in targets
    by resolving the references in sorted order"""
    return (common.get_path(ref, targets, include_key=True)
            for index, ref in _iterate_to_sentinel(references))

def _iterate_to_sentinel(source):
    """Generator expression that iterates over a dictionary of
    index=>reference pairs in sorted order until it reaches the sentinel
    reference and stops iteration.
    Items with a key that do not represent an integer are ignored."""
    for index, ref in sorted({int(k): v
                              for k, v in source.iteritems()
                              if common.is_numeric(k)}.iteritems()):
        path = _reference_path(ref)
        if _is_sentinel(path):
            break
        else:
            yield (index, path)

def _reference_path(ref):
    """Return the actual reference path (a list of path items to follow)
    for a reference item.
    The Netflix API sometimes adds another dict layer with a single key
    'reference' which we need to extract from."""
    if isinstance(ref, list):
        return ref
    elif isinstance(ref, dict) and 'reference' in ref:
        return ref['reference']
    else:
        raise InvalidReferenceError(
            'Unexpected reference format encountered: {}'.format(ref))

def _is_sentinel(ref):
    """Check if a reference item is of type sentinel and thus signals
    the end of the list"""
    return isinstance(ref, dict) and ref.get('$type') == 'sentinel'
