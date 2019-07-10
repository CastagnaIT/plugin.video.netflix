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
import sys
from time import time
from functools import wraps
try:
    import cPickle as pickle
except ImportError:
    import pickle

import xbmc
import xbmcgui
import xbmcvfs

CACHE_COMMON = 'cache_common'
CACHE_GENRES = 'cache_genres'
CACHE_SUPPLEMENTAL = 'cache_supplemental'
CACHE_METADATA = 'cache_metadata'
CACHE_INFOLABELS = 'cache_infolabels'
CACHE_ARTINFO = 'cache_artinfo'
CACHE_LIBRARY = 'library'

BUCKET_NAMES = [CACHE_COMMON, CACHE_GENRES, CACHE_SUPPLEMENTAL, CACHE_METADATA,
                CACHE_INFOLABELS, CACHE_ARTINFO, CACHE_LIBRARY]

BUCKET_LOCKED = 'LOCKED_BY_{:04d}_AT_{}'

# 100 years TTL should be close enough to infinite
TTL_INFINITE = 60 * 60 * 24 * 365 * 100


class CacheMiss(Exception):
    """Requested item is not in the cache"""
    pass


class UnknownCacheBucketError(Exception):
    """The requested cahce bucket does ot exist"""
    pass


'''
Logic to get the identifier
cache_output: called without params, use the first argument value of the function as identifier
cache_output: with identify_from_kwarg_name specified - get value identifier from kwarg name specified, if None value fallback to first function argument value

identify_append_from_kwarg_name - if specified append the value after the kwarg identify_from_kwarg_name, to creates a more specific identifier
identify_fallback_arg_index - to change the default fallback arg index (0), where the identifier get the value from the func arguments
fixed_identifier - note if specified all other params are ignored
'''


def cache_output(g, bucket, fixed_identifier=None,
                 identify_from_kwarg_name='videoid',
                 identify_append_from_kwarg_name=None,
                 identify_fallback_arg_index=0,
                 ttl=None,
                 to_disk=False):
    """Decorator that ensures caching the output of a function"""
    # pylint: disable=missing-docstring, invalid-name, too-many-arguments
    def caching_decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                identifier = _get_identifier(fixed_identifier,
                                             identify_from_kwarg_name,
                                             identify_append_from_kwarg_name,
                                             identify_fallback_arg_index,
                                             args,
                                             kwargs)
                if not identifier:
                    # Do not cache if identifier couldn't be determined
                    return func(*args, **kwargs)
                return g.CACHE.get(bucket, identifier)
            except CacheMiss:
                output = func(*args, **kwargs)
                g.CACHE.add(bucket, identifier, output, ttl=ttl,
                            to_disk=to_disk)
                return output
        return wrapper
    return caching_decorator


def _get_identifier(fixed_identifier, identify_from_kwarg_name,
                    identify_append_from_kwarg_name, identify_fallback_arg_index, args, kwargs):
    """Return the identifier to use with the caching_decorator"""
    # import resources.lib.common as common
    # common.debug('Get_identifier args: {}'.format(args))
    # common.debug('Get_identifier kwargs: {}'.format(kwargs))
    if fixed_identifier:
        identifier = fixed_identifier
    else:
        identifier = kwargs.get(identify_from_kwarg_name)
        if identifier and identify_append_from_kwarg_name and kwargs.get(identify_append_from_kwarg_name):
            identifier = identifier + '_' + kwargs.get(identify_append_from_kwarg_name)
        if not identifier and len(args) > 0:
            identifier = args[identify_fallback_arg_index]
    # common.debug('Get_identifier identifier value: {}'.format(identifier if identifier else 'None'))
    return identifier


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
    def __init__(self, common, cache_path, ttl, metadata_ttl, plugin_handle):
        # pylint: disable=too-many-arguments
        # We have the self.common module injected as a dependency to work
        # around circular dependencies with gloabl variable initialization
        self.common = common
        self.plugin_handle = plugin_handle
        self.cache_path = cache_path
        self.ttl = ttl
        self.metadata_ttl = metadata_ttl
        self.buckets = {}
        self.window = xbmcgui.Window(10000)

    def lock_marker(self, bucket):
        """Return a lock marker for this instance and the current time"""
        # Return maximum timestamp for library to prevent stale lock
        # overrides which may lead to inconsistencies
        timestamp = sys.maxint if bucket == CACHE_LIBRARY else int(time())
        return str(BUCKET_LOCKED.format(self.plugin_handle, timestamp))

    def get(self, bucket, identifier):
        """Retrieve an item from a cache bucket"""
        try:
            cache_entry = self._get_bucket(bucket)[identifier]
        except KeyError:
            cache_entry = self._get_from_disk(bucket, identifier)
            self.add(bucket, identifier, cache_entry['content'])
        # Do not verify TTL on cache library, prevents the loss of exported objects
        if not bucket == CACHE_LIBRARY:
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
        self.common.debug('Cache commit successful')

    def invalidate(self, on_disk=False):
        """Clear all cache buckets"""
        # pylint: disable=global-statement
        for bucket in BUCKET_NAMES:
            if bucket == CACHE_LIBRARY:
                continue
            self.window.clearProperty(_window_property(bucket))
            if bucket in self.buckets:
                del self.buckets[bucket]

        if on_disk:
            self._invalidate_on_disk()
        self.common.info('Cache invalidated')

    def _invalidate_on_disk(self):
        for bucket in BUCKET_NAMES:
            if bucket != CACHE_LIBRARY:
                self.common.delete_folder_contents(
                    os.path.join(self.cache_path, bucket))

    def invalidate_entry(self, bucket, identifier, on_disk=False):
        """Remove an item from a bucket"""
        try:
            self._purge_entry(bucket, identifier, on_disk)
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
        self._lock(bucket)
        self.common.debug('Acquired lock on {}'.format(bucket))
        return bucket_instance

    def _lock(self, bucket):
        self.window.setProperty(_window_property(bucket),
                                self.lock_marker(bucket))

    def _get_from_disk(self, bucket, identifier):
        """Load a cache entry from disk and add it to the in memory bucket"""
        handle = xbmcvfs.File(self._entry_filename(bucket, identifier), 'r')
        try:
            return pickle.loads(handle.read())
        except Exception:
            raise CacheMiss()
        finally:
            handle.close()

    def _add_to_disk(self, bucket, identifier, cache_entry):
        """Write a cache entry to disk"""
        # pylint: disable=broad-except
        cache_filename = self._entry_filename(bucket, identifier)
        handle = xbmcvfs.File(cache_filename, 'w')
        try:
            return pickle.dump(cache_entry, handle)
        except Exception as exc:
            self.common.error('Failed to write cache entry to {}: {}'
                              .format(cache_filename, exc))
        finally:
            handle.close()

    def _entry_filename(self, bucket, identifier):
        if bucket == CACHE_LIBRARY:
            # We want a special handling for the library database, so users
            # dont accidentally delete it when deleting the cache
            file_loc = [os.path.dirname(self.cache_path), 'library.ndb2']
        else:
            file_loc = [self.cache_path, bucket, '{}.cache'.format(identifier)]
        return xbmc.translatePath(os.path.join(*file_loc))

    def _persist_bucket(self, bucket, contents):
        # pylint: disable=broad-except
        if not self.is_safe_to_persist(bucket):
            self.common.warn(
                '{} is locked by another instance. Discarding changes'
                .format(bucket))
            return

        try:
            self.window.setProperty(_window_property(bucket),
                                    pickle.dumps(contents))
        except Exception as exc:
            self.common.error('Failed to persist {} to wnd properties: {}'
                              .format(bucket, exc))
            self.window.clearProperty(_window_property(bucket))
        finally:
            self.common.debug('Released lock on {}'.format(bucket))

    def is_safe_to_persist(self, bucket):
        # Only persist if we acquired the original lock or if the lock is older
        # than 15 seconds (override stale locks)
        lock = self.window.getProperty(_window_property(bucket))
        is_own_lock = lock[:14] == self.lock_marker(bucket)[:14]
        try:
            is_stale_lock = int(lock[18:] or 1) <= time() - 15
        except ValueError:
            is_stale_lock = False
        if is_stale_lock:
            self.common.info('Overriding stale cache lock {} on {}'
                             .format(lock, bucket))
        return is_own_lock or is_stale_lock

    def verify_ttl(self, bucket, identifier, cache_entry):
        """Verify if cache_entry has reached its EOL.
        Remove from in-memory and disk cache if so and raise CacheMiss"""
        if cache_entry['eol'] < int(time()):
            self.common.debug('Cache entry {} in {} has expired => cache miss'
                              .format(identifier, bucket))
            self._purge_entry(bucket, identifier)
            raise CacheMiss()

    def _purge_entry(self, bucket, identifier, on_disk=False):
        # To ensure removing disk cache, it must be loaded first or it will trigger an exception
        cache_filename = self._entry_filename(bucket, identifier)
        cache_exixts = os.path.exists(cache_filename)

        if on_disk and cache_exixts:
            cache_entry = self._get_from_disk(bucket, identifier)
            self.add(bucket, identifier, cache_entry['content'])

        # Remove from in-memory cache
        del self._get_bucket(bucket)[identifier]
        # Remove from disk cache if it exists

        if cache_exixts:
            os.remove(cache_filename)


def _window_property(bucket):
    return 'nfmemcache_{}'.format(bucket)
