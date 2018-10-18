# -*- coding: utf-8 -*-
"""Convenience representations of datatypes returned by the API"""
from __future__ import unicode_literals

class LoLoMo(object):
    """List of list of movies (lolomo)"""
    # pylint: disable=invalid-name
    def __init__(self, path_response):
        self.data = path_response['value']
        del self.data['null']

    @property
    def id(self):
        """ID of this LoLoMo"""
        return self.data['lolomo'][1]

    @property
    def lists(self):
        """Video lists referenced by this LoLoMo"""
        return [video_list
                for video_list in self.data['lists'].itervalues()]

    def lists_by_context(self, context):
        """Return a list of all video lists with the given context.
        Will match any video lists with type contained in context
        if context is a list."""
        if isinstance(context, list):
            lists = [video_list
                     for video_list in self.lists
                     if video_list['context'] in context]
        else:
            lists = [video_list
                     for video_list in self.lists
                     if video_list['context'] == context]
        return lists
