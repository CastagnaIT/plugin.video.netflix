# -*- coding: utf-8 -*-
"""Path info to query the Shakti pathEvaluator"""
from __future__ import unicode_literals

import resources.lib.common as common

ART_SIZE_POSTER = '_342x684'
ART_SIZE_FHD = '_1920x1080'
ART_SIZE_SD = '_665x375'

ART_PARTIAL_PATHS = [
    ['boxarts', [ART_SIZE_SD, ART_SIZE_FHD, ART_SIZE_POSTER], 'jpg'],
    ['interestingMoment', [ART_SIZE_SD, ART_SIZE_FHD], 'jpg'],
    ['storyarts', '_1632x873', 'jpg'],
    ['bb2OGLogo', '_550x124', 'png'],
    ['BGImages', '720', 'jpg']
]

VIDEO_LIST_PARTIAL_PATHS = [
    [['summary', 'title', 'synopsis', 'regularSynopsis', 'evidence', 'queue',
      'episodeCount', 'info', 'maturity', 'runtime', 'seasonCount',
      'releaseYear', 'userRating', 'numSeasonsLabel', 'bookmarkPosition',
      'watched', 'delivery']],
    [['genres', 'tags', 'creators', 'directors', 'cast'],
     {'from': 0, 'to': 10}, ['id', 'name']]
] + ART_PARTIAL_PATHS

SEASONS_PARTIAL_PATHS = [
    ['seasonList', {'from': 0, 'to': 40}, 'summary'],
    ['title']
] + ART_PARTIAL_PATHS

EPISODES_PARTIAL_PATHS = [
    [['summary', 'synopsis', 'title', 'runtime', 'releaseYear', 'queue',
      'info', 'maturity', 'userRating', 'bookmarkPosition', 'creditsOffset',
      'watched', 'delivery']],
    [['genres', 'tags', 'creators', 'directors', 'cast'],
     {'from': 0, 'to': 10}, ['id', 'name']]
] + ART_PARTIAL_PATHS

INFO_MAPPINGS = {
    'title': 'title',
    'year': 'releaseYear',
    'plot': 'synopsis',
    'season': ['summary', 'season'],
    'episode': ['summary', 'episode'],
    'rating': ['userRating', 'matchScore'],
    'userrating': ['userRating', 'userRating'],
    'mpaa': ['maturity', 'rating', 'value'],
    'duration': 'runtime',
    'bookmark': 'bookmarkPosition',
    'playcount': 'watched'
}

INFO_TRANSFORMATIONS = {
    'rating': lambda r: r / 10,
    'playcount': lambda w: int(w)
}

REFERENCE_MAPPINGS = {
    'cast': 'cast',
    'director': 'directors',
    'writer': 'creators',
    'genre': 'genres'
}

class InvalidReferenceError(Exception):
    """The provided reference cannot be dealt with as it is in an
    unexpected format"""
    pass

def resolve_refs(references, targets):
    """Return a generator expression that returns the objects in targets
    by resolving the references in sorted order"""
    return (common.get_path(ref, targets, include_key=True)
            for index, ref in iterate_to_sentinel(references))

def iterate_to_sentinel(source):
    """Generator expression that iterates over a dictionary of
    index=>reference pairs in sorted order until it reaches the sentinel
    reference and stops iteration.
    Items with a key that do not represent an integer are ignored."""
    for index, ref in sorted({int(k): v
                              for k, v in source.iteritems()
                              if common.is_numeric(k)}.iteritems()):
        path = reference_path(ref)
        if is_sentinel(path):
            break
        else:
            yield (index, path)

def reference_path(ref):
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

def is_sentinel(ref):
    """Check if a reference item is of type sentinel and thus signals
    the end of the list"""
    return isinstance(ref, dict) and ref.get('$type') == 'sentinel'
