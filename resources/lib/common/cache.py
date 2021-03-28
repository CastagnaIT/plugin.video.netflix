# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2020 Stefano Gottardo (original implementation module)
    Cache IPC interface - allow access to the add-on service cache from an add-on "frontend" instance

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from resources.lib.common import make_call, IPC_ENDPOINT_CACHE


class Cache:
    """Cache IPC interface"""

    def get(self, bucket, identifier):
        """Get a item from cache bucket"""
        call_args = {
            'bucket': bucket,
            'identifier': identifier
        }
        return make_call('get', call_args, IPC_ENDPOINT_CACHE)

    def add(self, bucket, identifier, data, ttl=None, expires=None, delayed_db_op=False):
        """
        Add or update an item to a cache bucket

        :param bucket: bucket where save the data
        :param identifier: key identifier of the data
        :param data: the content
        :param ttl: override default expiration (in seconds)
        :param expires: override default expiration (in timestamp) if specified override also the 'ttl' value
        :param delayed_db_op: if True, queues the adding operation for the db, then is mandatory to call
                      'execute_pending_db_add' at end of all operations to apply the changes to the db
                      (only for persistent buckets)
        """
        call_args = {
            'bucket': bucket,
            'identifier': identifier,
            'data': data,
            'ttl': ttl,
            'expires': expires,
            'delayed_db_op': delayed_db_op
        }
        make_call('add', call_args, IPC_ENDPOINT_CACHE)

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
        make_call('delete', call_args, IPC_ENDPOINT_CACHE)

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
        make_call('clear', call_args, IPC_ENDPOINT_CACHE)
