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
from __future__ import absolute_import, division, unicode_literals
import os
import sys
from time import time
from functools import wraps
from future.utils import iteritems

try:
    import cPickle as pickle
except ImportError:
    import pickle

import xbmc
import xbmcgui
import xbmcvfs

try:  # Python 2
    unicode
except NameError:  # Python 3
    unicode = str  # pylint: disable=redefined-builtin

CACHE_COMMON = 'cache_common'
CACHE_GENRES = 'cache_genres'
CACHE_SUPPLEMENTAL = 'cache_supplemental'
CACHE_METADATA = 'cache_metadata'
CACHE_INFOLABELS = 'cache_infolabels'
CACHE_ARTINFO = 'cache_artinfo'
CACHE_MANIFESTS = 'cache_manifests'

BUCKET_NAMES = [CACHE_COMMON, CACHE_GENRES, CACHE_SUPPLEMENTAL, CACHE_METADATA,
                CACHE_INFOLABELS, CACHE_ARTINFO, CACHE_MANIFESTS]

BUCKET_LOCKED = 'LOCKED_BY_{:04d}_AT_{}'

# 100 years TTL should be close enough to infinite
TTL_INFINITE = 60 * 60 * 24 * 365 * 100


class CacheMiss(Exception):
    """Requested item is not in the cache"""


class UnknownCacheBucketError(Exception):
    """The requested cache bucket does not exist"""


# Logic to get the identifier
# cache_output: called without params, use the first argument value of the function as identifier
# cache_output: with identify_from_kwarg_name, get value identifier from kwarg name specified,
#               if None value fallback to first function argument value

# identify_append_from_kwarg_name - if specified append the value after the kwarg identify_from
#                                  _kwarg_name, to creates a more specific identifier
# identify_fallback_arg_index - to change the default fallback arg index (0), where the identifier
#                               get the value from the func arguments
# fixed_identifier - note if specified all other params are ignored

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
    # common.debug('Get_identifier args: {}', args)
    # common.debug('Get_identifier kwargs: {}', kwargs)
    if fixed_identifier:
        identifier = fixed_identifier
    else:
        identifier = kwargs.get(identify_from_kwarg_name)
        if not identifier and args:
            identifier = args[identify_fallback_arg_index]
        if identifier and identify_append_from_kwarg_name and \
           kwargs.get(identify_append_from_kwarg_name):
            identifier += '_' + kwargs.get(identify_append_from_kwarg_name)
    # common.debug('Get_identifier identifier value: {}', identifier if identifier else 'None')
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
        self.PY_IS_VER2 = sys.version_info.major == 2

    def lock_marker(self):
        """Return a lock marker for this instance and the current time"""
        # Return maximum timestamp for library to prevent stale lock
        # overrides which may lead to inconsistencies
        timestamp = int(time())
        return BUCKET_LOCKED.format(self.plugin_handle, timestamp)

    def get(self, bucket, identifier, use_disk_fallback=True):
        """Retrieve an item from a cache bucket"""
        try:
            cache_entry = self._get_bucket(bucket)[identifier]
        except KeyError:
            if not use_disk_fallback:
                raise CacheMiss()
            cache_entry = self._get_from_disk(bucket, identifier)
            self.add(bucket, identifier, cache_entry['content'])
        self.verify_ttl(bucket, identifier, cache_entry)
        return cache_entry['content']

    def add(self, bucket, identifier, content, ttl=None, to_disk=False, eol=None):
        """Add an item to a cache bucket"""
        # pylint: disable=too-many-arguments
        if not eol:
            eol = int(time() + (ttl if ttl else self.ttl))
        # self.common.debug('Adding {} to {} (valid until {})',
        #                   identifier, bucket, eol)
        cache_entry = {'eol': eol, 'content': content}
        self._get_bucket(bucket).update(
            {identifier: cache_entry})
        if to_disk:
            self._add_to_disk(bucket, identifier, cache_entry)

    def commit(self):
        """Persist cache contents in window properties"""
        # pylint: disable=global-statement
        for bucket, contents in iteritems(self.buckets):
            self._persist_bucket(bucket, contents)
            # The self.buckets dict survives across addon invocations if the
            # same languageInvoker thread is being used so we MUST clear its
            # contents to allow cache consistency between instances
            # del self.buckets[bucket]
        self.common.debug('Cache commit successful')

    def invalidate(self, on_disk=False, bucket_names=None):
        """Clear all cache buckets"""
        # pylint: disable=global-statement
        if not bucket_names:
            bucket_names = BUCKET_NAMES
        for bucket in bucket_names:
            self.window.clearProperty(_window_property(bucket))
            if bucket in self.buckets:
                del self.buckets[bucket]

        if on_disk:
            self._invalidate_on_disk(bucket_names)
        self.common.info('Cache invalidated')

    def _invalidate_on_disk(self, bucket_names):
        for bucket in bucket_names:
            self.common.delete_folder_contents(
                os.path.join(self.cache_path, bucket))

    def invalidate_entry(self, bucket, identifier, on_disk=False):
        """Remove an item from a bucket"""
        try:
            self._purge_entry(bucket, identifier, on_disk)
            self.common.debug('Invalidated {} in {}', identifier, bucket)
        except KeyError:
            self.common.debug('Nothing to invalidate, {} was not in {}', identifier, bucket)

    def _get_bucket(self, key):
        """Get a cache bucket.
        Load it lazily from window property if it's not yet in memory"""
        if key not in BUCKET_NAMES:
            raise UnknownCacheBucketError()
        if key not in self.buckets:
            self.buckets[key] = self._load_bucket(key)
        return self.buckets[key]

    def _load_bucket(self, bucket):
        # Try 10 times to acquire a lock
        for _ in range(1, 10):
            wnd_property_data = self.window.getProperty(_window_property(bucket))
            if wnd_property_data.startswith(str('LOCKED_BY_')):
                self.common.debug('Waiting for release of {}', bucket)
                xbmc.sleep(50)
            else:
                return self._load_bucket_from_wndprop(bucket, wnd_property_data)
        self.common.warn('{} is locked. Working with an empty instance...', bucket)
        return {}

    def _load_bucket_from_wndprop(self, bucket, wnd_property_data):
        try:
            if self.PY_IS_VER2:
                # pickle.loads on py2 wants string
                bucket_instance = pickle.loads(wnd_property_data)
            else:
                bucket_instance = pickle.loads(wnd_property_data.encode('latin-1'))
        except Exception:  # pylint: disable=broad-except
            # When window.getProperty does not have the property here happen an error
            self.common.debug('No instance of {} found. Creating new instance.'.format(bucket))
            bucket_instance = {}
        self._lock(bucket)
        self.common.debug('Acquired lock on {}', bucket)
        return bucket_instance

    def _lock(self, bucket):
        self.window.setProperty(_window_property(bucket), self.lock_marker())

    def _get_from_disk(self, bucket, identifier):
        """Load a cache entry from disk and add it to the in memory bucket"""
        cache_filename = self._entry_filename(bucket, identifier)
        if not xbmcvfs.exists(cache_filename):
            raise CacheMiss()
        handle = xbmcvfs.File(cache_filename, 'rb')
        try:
            if self.PY_IS_VER2:
                # pickle.loads on py2 wants string
                return pickle.loads(handle.read())
            # py3
            return pickle.loads(handle.readBytes())
        except Exception as exc:
            self.common.error('Failed get cache from disk {}: {}', cache_filename, exc)
            raise CacheMiss()
        finally:
            handle.close()

    def _add_to_disk(self, bucket, identifier, cache_entry):
        """Write a cache entry to disk"""
        cache_filename = self._entry_filename(bucket, identifier)
        handle = xbmcvfs.File(cache_filename, 'wb')
        try:
            # return pickle.dump(cache_entry, handle)
            handle.write(bytearray(pickle.dumps(cache_entry)))
        except Exception as exc:  # pylint: disable=broad-except
            self.common.error('Failed to write cache entry to {}: {}', cache_filename, exc)
        finally:
            handle.close()

    def _entry_filename(self, bucket, identifier):
        file_loc = [self.cache_path, bucket, '{}.cache'.format(identifier)]
        return xbmc.translatePath(os.path.join(*file_loc))

    def _persist_bucket(self, bucket, contents):
        if not self.is_safe_to_persist(bucket):
            self.common.warn(
                '{} is locked by another instance. Discarding changes'
                .format(bucket))
            return
        try:
            if self.PY_IS_VER2 == 2:
                self.window.setProperty(_window_property(bucket), pickle.dumps(contents))
            else:
                # Note: On python 3 pickle.dumps produces byte not str cannot be passed as is in
                # setProperty because cannot receive arbitrary byte sequences if they contain
                # null bytes \x00, the stored value will be truncated by this null byte (Kodi bug).
                # To store pickled data in Python 3, you should use protocol 0 explicitly and decode
                # the resulted value with latin-1 encoding to str and then pass it to setPropety.
                self.window.setProperty(_window_property(bucket),
                                        pickle.dumps(contents, protocol=0).decode('latin-1'))
        except Exception as exc:  # pylint: disable=broad-except
            self.common.error('Failed to persist {} to wnd properties: {}', bucket, exc)
            self.window.clearProperty(_window_property(bucket))
        finally:
            self.common.debug('Released lock on {}', bucket)

    def is_safe_to_persist(self, bucket):
        # Only persist if we acquired the original lock or if the lock is older
        # than 15 seconds (override stale locks)
        lock_data = self.window.getProperty(_window_property(bucket))
        if lock_data.startswith(str('LOCKED_BY_')):
            # Eg. LOCKED_BY_0001_AT_1574951301
            # Check if is same add-on invocation: 'LOCKED_BY_0001'
            is_own_lock = lock_data[:14] == self.lock_marker()[:14]
            try:
                # Check if is time is older then 15 sec (last part after AT_)
                is_stale_lock = int(lock_data[18:] or 1) <= time() - 15
            except ValueError:
                is_stale_lock = False
            if is_stale_lock:
                self.common.info('Overriding stale cache lock {} on {}', lock_data, bucket)
            return is_own_lock or is_stale_lock
        return True

    def verify_ttl(self, bucket, identifier, cache_entry):
        """Verify if cache_entry has reached its EOL.
        Remove from in-memory and disk cache if so and raise CacheMiss"""
        if cache_entry['eol'] < int(time()):
            self.common.debug('Cache entry {} in {} has expired => cache miss',
                              identifier, bucket)
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
