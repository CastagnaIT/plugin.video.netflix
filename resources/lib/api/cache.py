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

COMMON = 'common'
VIDEO_LIST = 'video_list'
SEASONS = 'seasons'
EPISODES = 'episodes'
METADATA = 'metadata'

BUCKET_NAMES = [COMMON, VIDEO_LIST, SEASONS, EPISODES, METADATA]
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
    """Cache the output of a function"""
    # pylint: disable=missing-docstring
    def caching_decorator(func):
        @wraps
        def wrapper(*args, **kwargs):
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

def invalidate():
    """Clear all cache buckets"""
    # pylint: disable=global-statement
    global BUCKETS
    for bucket in BUCKETS:
        _clear_bucket(bucket)
    BUCKETS = {}

def invalidate_entry(bucket, identifier):
    """Remove an item from a bucket"""
    del get_bucket(bucket)[identifier]

def commit():
    """Persist cache contents in window properties"""
    for bucket, contents in BUCKETS.iteritems():
        _persist_bucket(bucket, contents)

def get(bucket, identifier):
    """Retrieve an item from a cache bucket"""
    try:
        cache_entry = get_bucket(bucket)[identifier]
    except KeyError:
        common.debug('Cache miss on {} in bucket {}'
                     .format(identifier, bucket))
        raise CacheMiss()

    if cache_entry['eol'] >= int(time()):
        common.debug('Cache entry {} in {} has expired'
                     .format(identifier, bucket))
        raise CacheMiss()

    return cache_entry['content']

def add(bucket, identifier, content):
    """Add an item to a cache bucket"""
    eol = int(time() + 600)
    get_bucket(bucket).update(
        {identifier: {'eol': eol, 'content': content}})

def _window_property(bucket):
    return 'nfmemcache_{}'.format(bucket)

def _load_bucket(bucket):
    # pylint: disable=broad-except
    try:
        return pickle.loads(WND.getProperty(_window_property(bucket)))
    except Exception as exc:
        common.debug('Failed to load cache bucket: {exc}', exc)
        return OrderedDict()

def _persist_bucket(bucket, contents):
    # pylint: disable=broad-except
    try:
        WND.setProperty(_window_property(bucket), pickle.dumps(contents))
    except Exception as exc:
        common.error('Failed to persist cache bucket: {exc}', exc)

def _clear_bucket(bucket):
    WND.clearProperty(_window_property(bucket))
    del BUCKETS[bucket]
