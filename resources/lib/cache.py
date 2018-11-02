# -*- coding: utf-8 -*-
"""General caching facilities. Caches are segmented into buckets.
Within each bucket, identifiers for cache entries must be unique.

Must not be used within these modules, because stale values may
be used and cause inconsistencies:
resources.lib.self.common
resources.lib.services
resources.lib.kodi.ui
resources.lib.services.nfsession
"""
from __future__ import unicode_literals

import os
from time import time
from functools import wraps
try:
    import cPickle as pickle
except ImportError:
    import pickle

import xbmc
import xbmcgui

CACHE_COMMON = 'cache_common'
CACHE_GENRES = 'cache_genres'
CACHE_METADATA = 'cache_metadata'
CACHE_INFOLABELS = 'cache_infolabels'
CACHE_ARTINFO = 'cache_artinfo'
CACHE_LIBRARY = 'library'

BUCKET_NAMES = [CACHE_COMMON, CACHE_GENRES, CACHE_METADATA,
                CACHE_INFOLABELS, CACHE_ARTINFO, CACHE_LIBRARY]

BUCKET_LOCKED = 'LOCKED_BY_{}'

TTL_INFINITE = 60*60*24*365*100


class CacheMiss(Exception):
    """Requested item is not in the cache"""
    pass


class UnknownCacheBucketError(Exception):
    """The requested cahce bucket does ot exist"""
    pass


def cache_output(g, bucket, identifying_param_index=0,
                 identifying_param_name='videoid',
                 fixed_identifier=None,
                 ttl=None,
                 to_disk=False):
    """Decorator that ensures caching the output of a function"""
    # pylint: disable=missing-docstring, invalid-name, too-many-arguments
    def caching_decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                identifier = _get_identifier(fixed_identifier,
                                             identifying_param_name,
                                             kwargs,
                                             identifying_param_index,
                                             args)
                cached_result = g.CACHE.get(bucket, identifier)
                return cached_result
            except CacheMiss:
                output = func(*args, **kwargs)
                g.CACHE.add(bucket, identifier, output, ttl=ttl,
                            to_disk=to_disk)
                return output
            except IndexError:
                # Do not cache if identifier couldn't be determined
                return func(*args, **kwargs)
        return wrapper
    return caching_decorator


def _get_identifier(fixed_identifier, identifying_param_name, kwargs,
                    identifying_param_index, args):
    """Return the identifier to use with the caching_decorator"""
    return (fixed_identifier
            if fixed_identifier
            else kwargs.get(identifying_param_name,
                            args[identifying_param_index]))


# def inject_from_cache(cache, bucket, injection_param,
#                       identifying_param_index=0,
#                       identifying_param_name=None,
#                       fixed_identifier=None,
#                       to_disk=False):
#     """Decorator that injects a cached value as parameter if available.
#     The decorated function must return a value to be added to the cache."""
#     # pylint: disable=missing-docstring
#     def injecting_cache_decorator(func):
#         @wraps(func)
#         def wrapper(*args, **kwargs):
#             identifier = _get_identifier(fixed_identifier,
#                                          identifying_param_name,
#                                          kwargs,
#                                          identifying_param_index,
#                                          args)
#             try:
#                 value_to_inject = cache.get(bucket, identifier)
#             except CacheMiss:
#                 value_to_inject = None
#             kwargs[injection_param] = value_to_inject
#             output = func(*args, **kwargs)
#             cache.add(bucket, identifier, output, ttl=ttl, to_disk=to_disk)
#             return output
#         return wrapper
#     return injecting_cache_decorator


class Cache(object):
    def __init__(self, common, data_path, ttl, metadata_ttl, plugin_handle):
        # pylint: disable=too-many-arguments
        # We have the self.common module injected as a dependency to work
        # around circular dependencies with gloabl variable initialization
        self.common = common
        self.data_path = data_path
        self.ttl = ttl
        self.metadata_ttl = metadata_ttl
        self.buckets = {}
        self.lock_marker = str(BUCKET_LOCKED.format(plugin_handle))
        self.window = xbmcgui.Window(10000)
        self.common.debug('Cache instantiated')

    def get(self, bucket, identifier):
        """Retrieve an item from a cache bucket"""
        try:
            cache_entry = self._get_bucket(bucket)[identifier]
        except KeyError:
            cache_entry = self._get_from_disk(bucket, identifier)
            self.add(bucket, identifier, cache_entry['content'])
        self.verify_ttl(bucket, identifier, cache_entry)
        return cache_entry['content']

    def add(self, bucket, identifier, content, ttl=None, to_disk=False):
        """Add an item to a cache bucket"""
        # pylint: disable=too-many-arguments
        eol = int(time() + (ttl if ttl else self.ttl))
        # self.common.debug('Adding {} to {} (valid until {})'
        #              .format(identifier, bucket, eol))
        cache_entry = {'eol': eol, 'content': content}
        self._get_bucket(bucket).update(
            {identifier: cache_entry})
        if to_disk:
            self._add_to_disk(bucket, identifier, cache_entry)

    def commit(self):
        """Persist cache contents in window properties"""
        # pylint: disable=global-statement
        for bucket, contents in self.buckets.items():
            self._persist_bucket(bucket, contents)
            # The self.buckets dict survives across addon invocations if the
            # same languageInvoker thread is being used so we MUST clear its
            # contents to allow cache consistency between instances
            # del self.buckets[bucket]
        self.common.debug('Cache committ successful')

    def invalidate(self):
        """Clear all cache buckets"""
        # pylint: disable=global-statement
        for bucket in BUCKET_NAMES:
            self.window.clearProperty(_window_property(bucket))
        self.buckets = {}
        self.common.info('Cache invalidated')

    def invalidate_entry(self, bucket, identifier):
        """Remove an item from a bucket"""
        try:
            self._purge_entry(bucket, identifier)
            self.common.debug('Invalidated {} in {}'
                              .format(identifier, bucket))
        except KeyError:
            self.common.debug('Nothing to invalidate, {} was not in {}'
                              .format(identifier, bucket))

    def _get_bucket(self, key):
        """Get a cache bucket.
        Load it lazily from window property if it's not yet in memory"""
        if key not in BUCKET_NAMES:
            raise UnknownCacheBucketError()
        if key not in self.buckets:
            self.buckets[key] = self._load_bucket(key)
        return self.buckets[key]

    def _load_bucket(self, bucket):
        wnd_property = ''
        # Try 10 times to acquire a lock
        for _ in range(1, 10):
            wnd_property = self.window.getProperty(_window_property(bucket))
            # pickle stores byte data, so we must compare against a str
            if wnd_property.startswith(str('LOCKED')):
                self.common.debug('Waiting for release of {}'.format(bucket))
                xbmc.sleep(50)
            else:
                return self._load_bucket_from_wndprop(bucket, wnd_property)
        self.common.warn('{} is locked. Working with an empty instance...'
                         .format(bucket))
        return {}

    def _load_bucket_from_wndprop(self, bucket, wnd_property):
        # pylint: disable=broad-except
        try:
            bucket_instance = pickle.loads(wnd_property)
        except Exception:
            self.common.debug('No instance of {} found. Creating new instance.'
                              .format(bucket))
            bucket_instance = {}
        self.window.setProperty(_window_property(bucket), self.lock_marker)
        self.common.debug('Acquired lock on {}'.format(bucket))
        return bucket_instance

    def _get_from_disk(self, bucket, identifier):
        """Load a cache entry from disk and add it to the in memory bucket"""
        cache_filename = self._entry_filename(bucket, identifier)
        try:
            with open(cache_filename, 'r') as cache_file:
                cache_entry = pickle.load(cache_file)
        except Exception:
            raise CacheMiss()
        return cache_entry

    def _add_to_disk(self, bucket, identifier, cache_entry):
        """Write a cache entry to disk"""
        # pylint: disable=broad-except
        cache_filename = self._entry_filename(bucket, identifier)
        try:
            with open(cache_filename, 'w') as cache_file:
                pickle.dump(cache_entry, cache_file)
        except Exception as exc:
            self.common.error('Failed to write cache entry to {}: {}'
                              .format(cache_filename, exc))

    def _entry_filename(self, bucket, identifier):
        if bucket == CACHE_LIBRARY:
            # We want a special handling for the library database, so users
            # dont accidentally delete it when deleting the cache
            file_loc = ['library.ndb2']
        else:
            file_loc = [
                'cache', bucket, '{}.cache'.format(identifier)]
        return os.path.join(self.data_path, *file_loc)

    def _persist_bucket(self, bucket, contents):
        # pylint: disable=broad-except
        lock = self.window.getProperty(_window_property(bucket))
        # pickle stored byte data, so we must compare against a str
        if lock == self.lock_marker:
            try:
                self.window.setProperty(_window_property(bucket),
                                        pickle.dumps(contents))
            except Exception as exc:
                self.common.error('Failed to persist {} to wnd properties: {}'
                                  .format(bucket, exc))
                self.window.clearProperty(_window_property(bucket))
            finally:
                self.common.debug('Released lock on {}'.format(bucket))
        else:
            self.common.warn(
                '{} is locked by another instance. Discarding changes'
                .format(bucket))

    def verify_ttl(self, bucket, identifier, cache_entry):
        """Verify if cache_entry has reached its EOL.
        Remove from in-memory and disk cache if so and raise CacheMiss"""
        if cache_entry['eol'] < int(time()):
            self.common.debug('Cache entry {} in {} has expired => cache miss'
                              .format(identifier, bucket))
            self._purge_entry(bucket, identifier)
            raise CacheMiss()

    def _purge_entry(self, bucket, identifier):
        # Remove from in-memory cache
        del self._get_bucket(bucket)[identifier]
        # Remove from disk cache if it exists
        cache_filename = self._entry_filename(bucket, identifier)
        if os.path.exists(cache_filename):
            os.remove(cache_filename)


def _window_property(bucket):
    return 'nfmemcache_{}'.format(bucket)
