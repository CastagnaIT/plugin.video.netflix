# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    'Path' data and utility to query the Shakti API

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals
from future.utils import iteritems

import resources.lib.common as common

from .exceptions import InvalidReferenceError

MAX_PATH_REQUEST_SIZE = 47  # Stands for 48 results, is the default value defined by netflix for a single request

RANGE_SELECTOR = 'RANGE_SELECTOR'

ART_SIZE_POSTER = '_342x684'
ART_SIZE_FHD = '_1920x1080'
ART_SIZE_SD = '_665x375'

LENGTH_ATTRIBUTES = {
    'stdlist': lambda r, context, key: len(r[context][key]),
    'stdlist_wid': lambda r, context, uid, key: len(r[context][uid][key]),
    'searchlist': lambda r, context, key: len(list(r[context][key].values())[0]),
}

"""Predefined lambda expressions that return the number of video results within a path response dict"""

ART_PARTIAL_PATHS = [
    ['boxarts', [ART_SIZE_SD, ART_SIZE_FHD, ART_SIZE_POSTER], 'jpg'],
    ['interestingMoment', [ART_SIZE_SD, ART_SIZE_FHD], 'jpg'],
    ['storyarts', '_1632x873', 'jpg'],  # storyarts seem no more used, never found it in the results
    ['bb2OGLogo', '_550x124', 'png'],
    ['BGImages', '720', 'jpg']
]

VIDEO_LIST_PARTIAL_PATHS = [
    [['requestId', 'summary', 'title', 'synopsis', 'regularSynopsis', 'evidence', 'queue',
      'episodeCount', 'info', 'maturity', 'runtime', 'seasonCount',
      'releaseYear', 'userRating', 'numSeasonsLabel', 'bookmarkPosition', 'creditsOffset',
      'dpSupplementalMessage', 'watched', 'delivery', 'sequiturEvidence']],
    [['genres', 'tags', 'creators', 'directors', 'cast'],
     {'from': 0, 'to': 10}, ['id', 'name']]
] + ART_PARTIAL_PATHS

VIDEO_LIST_BASIC_PARTIAL_PATHS = [
    [['title', 'queue', 'watched', 'summary', 'type', 'id']]
]

GENRE_PARTIAL_PATHS = [
    [["id", "requestId", "summary", "name"]],
    [{"from": 0, "to": 50},
     ["context", "displayName", "genreId", "id", "isTallRow", "length",
      "requestId", "type", "videoId"]]
]

SEASONS_PARTIAL_PATHS = [
    ['seasonList', RANGE_SELECTOR, 'summary'],
    ['title']
] + ART_PARTIAL_PATHS

EPISODES_PARTIAL_PATHS = [
    [['requestId', 'summary', 'synopsis', 'title', 'runtime', 'releaseYear', 'queue',
      'info', 'maturity', 'userRating', 'bookmarkPosition', 'creditsOffset',
      'watched', 'delivery', 'trackIds']],
    [['genres', 'tags', 'creators', 'directors', 'cast'],
     {'from': 0, 'to': 10}, ['id', 'name']]
] + ART_PARTIAL_PATHS

TRAILER_PARTIAL_PATHS = [
    [['availability', 'summary', 'synopsis', 'title', 'trackId', 'delivery', 'runtime',
      'bookmarkPosition', 'creditsOffset']]
] + ART_PARTIAL_PATHS

EVENT_PATHS = [
    [['requestId', 'title', 'runtime', 'queue', 'bookmarkPosition', 'watched', 'trackIds']]
]

VIDEO_LIST_RATING_THUMB_PATHS = [
    [['summary', 'title', 'userRating', 'trackIds']]
]

SUPPLEMENTAL_TYPE_TRAILERS = 'trailers'

INFO_MAPPINGS = {
    'title': 'title',
    'year': 'releaseYear',
    'plot': 'synopsis',
    'season': ['summary', 'season'],
    'season_shortname': ['summary', 'shortName'],  # Add info to item listings._create_season_item
    'episode': ['summary', 'episode'],
    'rating': ['userRating', 'matchScore'],
    'userrating': ['userRating', 'userRating'],
    'mpaa': ['maturity', 'rating', 'value'],
    'duration': 'runtime',
    # 'bookmark': 'bookmarkPosition',
    # 'playcount': 'watched'
}

INFO_TRANSFORMATIONS = {
    'season_shortname': lambda sn: ''.join([n for n in sn if n.isdigit()]),
    'rating': lambda r: r / 10,
    'playcount': lambda w: int(w)  # pylint: disable=unnecessary-lambda
}

REFERENCE_MAPPINGS = {
    'cast': 'cast',
    'director': 'directors',
    'writer': 'creators',
    'genre': 'genres'
}


def build_paths(base_path, partial_paths):
    """Build a list of full paths by concatenating each partial path with the base path"""
    paths = [base_path + partial_path for partial_path in partial_paths]
    return paths


def resolve_refs(references, targets):
    """Return a generator expression that returns the objects in targets
    by resolving the references in sorted order"""
    return (common.get_path(ref, targets, include_key=True)
            for index, ref in iterate_references(references))


def iterate_references(source):
    """Generator expression that iterates over a dictionary of
    index=>reference pairs (sorted in ascending order by indices) until it
    reaches the first empty reference, which signals the end of the reference
    list.
    Items with a key that do not represent an integer are ignored."""
    for index, ref in sorted({int(k): v
                              for k, v in iteritems(source)
                              if common.is_numeric(k)}.items()):
        path = reference_path(ref)
        if path is None:
            break
        if path[0] == 'characters':
            # TODO: Implement handling of character references in Kids profiles
            continue
        yield (index, path)


def count_references(source):
    counter = 0
    for index, ref in sorted({int(k): v  # pylint: disable=unused-variable
                              for k, v in iteritems(source)
                              if common.is_numeric(k)}.items()):
        path = reference_path(ref)

        if path is None:
            continue
        if path[0] == 'characters':
            continue
        counter += 1
    return counter


def reference_path(ref):
    """Return the actual reference path (a list of path items to follow)
    for a reference item.

    The Netflix API returns references in several different formats.
    In both cases, we want to get at the innermost list, which describes
    the path to follow when resolving the reference:
    - List-based references:
        [
          "lists",
          "09a4eb6f-8f6b-45fe-a65b-c64c4fcdc6b8_60070239X20XX1539870260807"
        ]
    - Dict-based references which have a type and a value:
        {
          "$type": "ref",
          "value": [
            "videos",
            "80018294"
          ]
        }

    Empty references indicate the end of a list of references if there
    are fewer entries available than were requested. They are always a dict,
    regardless of valid references in the list being list-based or dict-based.
    They don't have a value attribute and are either of type sentinel or atom:
        { "$type": "sentinel" }
            or
        { "$type": "atom" }

    In some cases, references are requested via the 'reference' attribute of
    a Netlix list type like so:
        ["genres", "83", "rw", "shortform",
         { "from": 0, "to": 50 },
         { "from": 0, "to": 7 },
         "reference",
         "ACTUAL ATTRIBUTE OF REFERENCED ITEM"]
    In this case, the reference we want to get the value of is nested into an
    additional 'reference' attribute like so:
        - list-based nested reference:
            {
                "reference": [      <== additional nesting
                    "videos",
                    "80178971"
                ]
            }
        - dict-based nested reference:
            {
              "reference": {        <== additional nesting
                "$type": "ref",
                "value": [
                  "videos",
                  "80018294"
                ]
              }
            }
    To get to the value, we simply remove the additional layer of nesting by
    doing ref = ref['reference'] and continue with analyzing ref.
    """
    ref = _remove_nesting(ref)
    if isinstance(ref, list):
        return ref
    if isinstance(ref, dict):
        return ref['value'] if ref.get('$type') == 'ref' else None
    raise InvalidReferenceError(
        'Unexpected reference format encountered: {}'.format(ref))


def _remove_nesting(ref):
    """Remove the outer layer of nesting if ref is a nested reference.
    Return the original reference if it's not nested"""
    return (ref['reference']
            if isinstance(ref, dict) and 'reference' in ref
            else ref)
