# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2020 Stefano Gottardo (original implementation module)
    Caching facilities. Caches are segmented into buckets.
    Within each bucket, identifiers for cache entries must be unique.

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

from resources.lib.common import make_http_call_cache
from resources.lib.common.cache_utils import deserialize_data, serialize_data
from resources.lib.globals import g


class Cache(object):
    """Cache"""
    # All the cache is automatically allocated by profile by using a prefix in the cache identifier
    # and the data remains in memory until the service will be stopped (if it is not specified as persistent)

    # The persistent cache option:
    # This option will enable to save/read the cache data in a database (see cache_management.py)
    # When a cache bucket is set as 'persistent', allow to the cache data to survive events that stop the netflix
    # service for example: update of add-on, restart of Kodi or change Kodi profile.
    # This option can be enabled for each individual bucket,
    # by set 'is_persistent' to True in the bucket variable (see cache_utils.py)

    def __init__(self):
        self._make_call = _make_call_service if g.IS_SERVICE else _make_call_client

    def get(self, bucket, identifier):
        """Get a item from cache bucket"""
        call_args = {
            'bucket': bucket,
            'identifier': identifier
        }
        data = self._make_call('get', call_args)
        return deserialize_data(data)

    def add(self, bucket, identifier, data, ttl=None, expires=None):
        """
        Add or update an item to a cache bucket

        :param bucket: bucket where save the data
        :param identifier: key identifier of the data
        :param data: the content
        :param ttl: override default expiration (in seconds)
        :param expires: override default expiration (in timestamp) if specified override also the 'ttl' value
        """
        call_args = {
            'bucket': bucket,
            'identifier': identifier,
            'data': None,  # This value is injected after the _make_call
            'ttl': ttl,
            'expires': expires
        }
        self._make_call('add', call_args, serialize_data(data))

    def delete(self, bucket, identifier, including_suffixes=False):
        """
        Delete an item from cache bucket

        :param including_suffixes: if true will delete all items with the identifier that start with it
        """
        call_args = {
            'bucket': bucket,
            'identifier': identifier,
            'including_suffixes': including_suffixes
        }
        self._make_call('delete', call_args)

    def clear(self, buckets=None, clear_database=True):
        """
        Clear the cache

        :param buckets: list of buckets to clear, if not specified clear all the cache
        :param clear_database: if True clear also the database data
        """
        call_args = {
            'buckets': buckets,
            'clear_database': clear_database
        }
        self._make_call('clear', call_args)


def _make_call_client(callname, params=None, data=None):
    # In the client-frontend instance is needed to use the IPC cache http service
    return make_http_call_cache(callname, params, data)


def _make_call_service(callname, params=None, data=None):
    if 'data' in params:
        params['data'] = data
    # In the service instance direct call to cache management
    return getattr(g.CACHE_MANAGEMENT, callname)(**params)
