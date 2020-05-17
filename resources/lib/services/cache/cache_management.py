# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2020 Stefano Gottardo (original implementation module)
    Cache management

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import sqlite3 as sql
import threading
from datetime import datetime, timedelta
from functools import wraps
from time import time

from resources.lib import common
from resources.lib.api.exceptions import UnknownCacheBucketError, CacheMiss
from resources.lib.common import g
from resources.lib.database.db_exceptions import SQLiteConnectionError, SQLiteError, ProfilesMissing
from resources.lib.common.cache_utils import BUCKET_NAMES, BUCKETS

CONN_ISOLATION_LEVEL = None  # Autocommit mode


def handle_connection(func):
    """A decorator that handle the connection status with the database"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        conn = None
        try:
            if not args[0].is_connected:
                args[0].mutex.acquire()
                args[0].conn = sql.connect(args[0].db_file_path, isolation_level=CONN_ISOLATION_LEVEL)
                args[0].is_connected = True
                conn = args[0].conn
            return func(*args, **kwargs)
        except sql.Error as exc:
            common.error('SQLite error {}:', exc.args[0])
            raise SQLiteConnectionError
        finally:
            if conn:
                args[0].is_connected = False
                conn.close()
                args[0].mutex.release()
    return wrapper


class CacheManagement(object):
    """Cache management"""

    def __init__(self):
        self._identifier_prefix = None
        self.mutex = threading.Lock()
        self.local_storage = threading.local()
        self.conn = None
        self.db_file_path = None
        self.memory_cache = {}
        self._initialize()
        self.next_schedule = _compute_next_schedule()

    @property
    def identifier_prefix(self):
        return self._identifier_prefix or self._set_identifier_prefix()

    @identifier_prefix.setter
    def identifier_prefix(self, val):
        self._identifier_prefix = val + '_'

    def _set_identifier_prefix(self):
        # Hundreds of cache accesses are made when loading video lists, then get the active profile guid
        # for each cache requests slows down the total time it takes to load e.g. the video list,
        # then we load the value on first access, and update it only at profile switch
        self._identifier_prefix = g.LOCAL_DB.get_active_profile_guid() + '_'
        return self._identifier_prefix

    def _add_prefix(self, identifier):
        return self.identifier_prefix + identifier

    @property
    def is_connected(self):
        return getattr(self.local_storage, 'is_connected', False)

    @is_connected.setter
    def is_connected(self, val):
        self.local_storage.is_connected = val

    def _initialize(self):
        from resources.lib.database.db_utils import get_local_db_path
        self.db_file_path = get_local_db_path('nf_cache.sqlite3')
        self.conn = sql.connect(self.db_file_path)
        self._create_table()

    def _create_table(self):
        cur = self.conn.cursor()
        table = str('CREATE TABLE IF NOT EXISTS cache_data ('
                    'bucket        TEXT NOT NULL,'
                    'identifier    TEXT NOT NULL,'
                    'value         BLOB,'
                    'expires       INT,'
                    'last_modified INT,'
                    'PRIMARY KEY (bucket, identifier));')
        cur.execute(table)
        self.conn.close()

    def on_service_tick(self):
        """Check if expired cache cleaning is due and trigger it"""
        if self.next_schedule <= datetime.now():
            common.debug('Triggering expired cache cleaning')
            self.delete_expired()
            g.LOCAL_DB.set_value('clean_cache_last_start', datetime.now())
            self.next_schedule = _compute_next_schedule()

    def _get_cache_bucket(self, bucket_name):
        """Get the data contained to a cache bucket"""
        if bucket_name not in self.memory_cache:
            if bucket_name not in BUCKET_NAMES:  # Verify only at the first time (something is wrong in source code)
                raise UnknownCacheBucketError()
            self.memory_cache[bucket_name] = {}
        return self.memory_cache[bucket_name]

    def get(self, bucket, identifier):
        """Get a item from cache bucket"""
        try:
            identifier = self._add_prefix(identifier)
            cache_entry = self._get_cache_bucket(bucket['name'])[identifier]
            if cache_entry['expires'] < int(time()):
                # Cache expired
                raise CacheMiss()
            return cache_entry['data']
        except KeyError:
            if bucket['is_persistent']:
                return self._get_db(bucket['name'], identifier)
            raise CacheMiss()
        except ProfilesMissing:
            # Raised by _add_prefix there is no active profile guid when add-on is installed from scratch
            raise CacheMiss()

    @handle_connection
    def _get_db(self, bucket_name, identifier):
        try:
            cursor = self.conn.cursor()
            query = ('SELECT value FROM cache_data '
                     'WHERE '
                     'expires > ? AND '
                     'bucket = ? AND identifier = ?')
            cursor.execute(query, (time(), bucket_name, identifier))
            result = cursor.fetchone()
            if result is None:
                raise CacheMiss()
            return result[0]
        except sql.Error as exc:
            common.error('SQLite error {}:', exc.args[0])
            raise SQLiteError

    def add(self, bucket, identifier, data, ttl=None, expires=None):
        """
        Add or update an item to a cache bucket

        :param bucket: bucket where save the data
        :param identifier: key identifier of the data
        :param data: the content
        :param ttl: override default expiration (in seconds)
        :param expires: override default expiration (in timestamp) if specified override also the 'ttl' value
        """
        try:
            identifier = self._add_prefix(identifier)
            if not expires:
                if not ttl and bucket['default_ttl']:
                    ttl = getattr(g, bucket['default_ttl'])
                expires = int(time() + ttl)
            cache_entry = {'expires': expires, 'data': data}
            # Save the item data to memory-cache
            self._get_cache_bucket(bucket['name']).update({identifier: cache_entry})
            if bucket['is_persistent']:
                # Save the item data to the cache database
                self._add_db(bucket['name'], identifier, data, expires)
        except ProfilesMissing:
            # Raised by _add_prefix there is no active profile guid when add-on is installed from scratch
            pass

    @handle_connection
    def _add_db(self, bucket_name, identifier, data, expires):
        try:
            cursor = self.conn.cursor()
            query = ('REPLACE INTO cache_data (bucket, identifier, value, expires, last_modified) '
                     'VALUES(?, ?, ?, ?, ?)')
            cursor.execute(query, (bucket_name, identifier, sql.Binary(data), expires, int(time())))
        except sql.Error as exc:
            common.error('SQLite error {}:', exc.args[0])
            raise SQLiteError

    def delete(self, bucket, identifier, including_suffixes):
        """
        Delete an item from cache bucket

        :param including_suffixes: if true will delete all items with the identifier that start with it
        """
        # Delete the item data from in memory-cache
        try:
            identifier = self._add_prefix(identifier)
            bucket_data = self._get_cache_bucket(bucket['name'])
            if including_suffixes:
                keys_to_delete = []
                for key_identifier in bucket_data.keys():
                    if key_identifier.startswith(identifier):
                        keys_to_delete.append(key_identifier)
                for key_identifier in keys_to_delete:
                    del bucket_data[key_identifier]
            else:
                if identifier in bucket_data:
                    del bucket_data[identifier]
            if bucket['is_persistent']:
                # Delete the item data from cache database
                self._delete_db(bucket['name'], identifier, including_suffixes)
        except ProfilesMissing:
            # Raised by _add_prefix there is no active profile guid when add-on is installed from scratch
            pass

    @handle_connection
    def _delete_db(self, bucket_name, identifier, including_suffixes):
        try:
            cursor = self.conn.cursor()
            if including_suffixes:
                identifier += '%'
                query = 'DELETE FROM cache_data WHERE bucket = ? AND identifier LIKE ?'
            else:
                query = 'DELETE FROM cache_data WHERE bucket = ? AND identifier = ?'
            cursor.execute(query, (bucket_name, identifier))
        except sql.Error as exc:
            common.error('SQLite error {}:', exc.args[0])
            raise SQLiteError

    def clear(self, buckets=None, clear_database=True):
        """
        Clear the cache

        :param buckets: list of buckets to clear, if not specified clear all the cache
        :param clear_database: if True clear also the database data
        """
        common.debug('Performing cache clearing')
        if buckets is None:
            # Clear all cache
            self.memory_cache = {}
            if clear_database:
                self._clear_db()
        else:
            # Clear only specified buckets
            for bucket in buckets:
                if bucket['name'] in self.memory_cache:
                    del self.memory_cache[bucket['name']]
                if clear_database:
                    self._clear_db(bucket)

    @handle_connection
    def _clear_db(self, bucket=None):
        try:
            cursor = self.conn.cursor()
            if bucket is None:
                query = 'DELETE FROM cache_data'
                cursor.execute(query)
            else:
                query = 'DELETE FROM cache_data WHERE bucket = ?'
                cursor.execute(query, (bucket['name'], ))
        except sql.Error as exc:
            common.error('SQLite error {}:', exc.args[0])
            raise SQLiteError

    def delete_expired(self):
        bucket_names_db = []
        timestamp = time()
        for bucket in BUCKETS:
            if bucket['is_persistent']:
                bucket_names_db.append(bucket['name'])
            bucket_content = self._get_cache_bucket(bucket['name'])
            for identifier, cache_entry in list(bucket_content.items()):  # pylint: disable=unused-variable
                if cache_entry['expires'] < timestamp:
                    del bucket_content['identifier']
        if bucket_names_db:
            self._delete_expired_db(bucket_names_db, timestamp)

    @handle_connection
    def _delete_expired_db(self, bucket_names, timestamp):
        query = 'DELETE FROM cache_data WHERE ('
        query += ' OR '.join(['bucket = ?'] * len(bucket_names))
        query += ') AND expires < ?'
        bucket_names.append(timestamp)
        try:
            cursor = self.conn.cursor()
            cursor.execute(query, bucket_names)
        except sql.Error as exc:
            common.error('SQLite error {}:', exc.args[0])
            raise SQLiteError


def _compute_next_schedule():
    last_run = g.LOCAL_DB.get_value('clean_cache_last_start', data_type=datetime)
    if last_run is None:
        last_run = datetime.now()
        g.LOCAL_DB.set_value('clean_cache_last_start', last_run)
    next_run = last_run + timedelta(days=15)
    return next_run
