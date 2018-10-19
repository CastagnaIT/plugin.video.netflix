# -*- coding: utf-8 -*-
"""Caching for API calls"""
from __future__ import unicode_literals

from time import time
from collections import OrderedDict
from functools import wraps
try:
    import cPickle as pickle
except ImportError:
    import pickle

import xbmcgui

import resources.lib.common as common

WND = xbmcgui.Window(10000)

CACHE_COMMON = 'cache_common'
CACHE_VIDEO_LIST = 'cache_video_list'
CACHE_SEASONS = 'cache_seasons'
CACHE_EPISODES = 'cache_episodes'
CACHE_METADATA = 'cache_metadata'

BUCKET_NAMES = [CACHE_COMMON, CACHE_VIDEO_LIST, CACHE_SEASONS,
                CACHE_EPISODES, CACHE_METADATA]
BUCKETS = {}

class CacheMiss(Exception):
    """Requested item is not in the cache"""
    pass

class UnknownCacheBucketError(Exception):
    """The requested cahce bucket does ot exist"""
    pass

def cache_output(bucket, identifying_param_index=0,
                 identifying_param_name=None,
                 fixed_identifier=None):
    """Decorator that ensures caching the output of a function"""
    # pylint: disable=missing-docstring
    def caching_decorator(func):
        common.debug('Decorating {} for caching'.format(func.__name__))
        @wraps(func)
        def wrapper(*args, **kwargs):
            common.debug('Calling {} with caching'.format(func.__name__))
            if fixed_identifier:
                identifier = fixed_identifier
            else:
                try:
                    # prefer keyword over positional arguments
                    identifier = kwargs.get(
                        identifying_param_name, args[identifying_param_index])
                except IndexError:
                    common.error(
                        'Invalid cache configuration.'
                        'Cannot determine identifier from params')
            try:
                return get(bucket, identifier)
            except CacheMiss:
                output = func(*args, **kwargs)
                add(bucket, identifier, output)
                return output
        return wrapper
    return caching_decorator

def get_bucket(key):
    """Get a cache bucket.
    Load it lazily from window property if it's not yet in memory"""
    if key not in BUCKET_NAMES:
        raise UnknownCacheBucketError()

    if key not in BUCKETS:
        BUCKETS[key] = _load_bucket(key)
    return BUCKETS[key]

def invalidate_cache():
    """Clear all cache buckets"""
    # pylint: disable=global-statement
    global BUCKETS
    for bucket in BUCKETS:
        _clear_bucket(bucket)
    BUCKETS = {}
    common.info('Cache invalidated')

def invalidate_entry(bucket, identifier):
    """Remove an item from a bucket"""
    del get_bucket(bucket)[identifier]
    common.debug('Invalidated {} in {}'.format(identifier, bucket))

def commit():
    """Persist cache contents in window properties"""
    for bucket, contents in BUCKETS.iteritems():
        _persist_bucket(bucket, contents)
    common.debug('Successfully persisted cache to window properties')

def get(bucket, identifier):
    """Retrieve an item from a cache bucket"""
    try:
        cache_entry = get_bucket(bucket)[identifier]
    except KeyError:
        common.debug('Cache miss on {} in bucket {}'
                     .format(identifier, bucket))
        raise CacheMiss()

    if cache_entry['eol'] < int(time()):
        common.debug('Cache entry {} in {} has expired => cache miss'
                     .format(identifier, bucket))
        del get_bucket(bucket)[identifier]
        raise CacheMiss()

    common.debug('Cache hit on {} in {}. Entry valid until {}'
                 .format(identifier, bucket, cache_entry['eol']))
    return cache_entry['content']

def add(bucket, identifier, content):
    """Add an item to a cache bucket"""
    eol = int(time() + common.CACHE_TTL)
    get_bucket(bucket).update(
        {identifier: {'eol': eol, 'content': content}})

def _window_property(bucket):
    return 'nfmemcache_{}'.format(bucket)

def _load_bucket(bucket):
    # pylint: disable=broad-except
    try:
        return pickle.loads(WND.getProperty(_window_property(bucket)))
    except Exception:
        common.debug('Failed to load cache bucket {}. Returning empty bucket.'
                     .format(bucket))
        return OrderedDict()

def _persist_bucket(bucket, contents):
    # pylint: disable=broad-except
    try:
        WND.setProperty(_window_property(bucket), pickle.dumps(contents))
    except Exception as exc:
        common.error('Failed to persist cache bucket: {exc}', exc)

def _clear_bucket(bucket):
    WND.clearProperty(_window_property(bucket))
