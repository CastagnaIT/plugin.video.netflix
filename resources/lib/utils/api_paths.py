# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    'Path' data and utility to query the Shakti API

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import resources.lib.common as common

from resources.lib.globals import G
from resources.lib.common.exceptions import InvalidReferenceError

# Limit size for the path request (with zero base)
# The requests to sorted lists can get more then 48 results,
# but the nf server blocks request if the response will result in too much data
PATH_REQUEST_SIZE_STD = 47  # Standard size defined by netflix, limit imposed to some fixed lists
PATH_REQUEST_SIZE_PAGINATED = 44  # Used to paginated results (value rounded for easy settings)
PATH_REQUEST_SIZE_MAX = 199

RANGE_PLACEHOLDER = 'RANGE_PLACEHOLDER'

ART_SIZE_POSTER = '_342x684'
ART_SIZE_FHD = '_1920x1080'
ART_SIZE_HD = '_1280x720'
ART_SIZE_SD = '_665x375'

LENGTH_ATTRIBUTES = {
    'stdlist': lambda r, context, key: jgrapgh_len(r[context][key]),
    'stdlist_wid': lambda r, context, uid, key: jgrapgh_len(r[context][uid][key]),
    'searchlist': lambda r, context, key: len(list(r[context][key].values())[0]),
}

"""Predefined lambda expressions that return the number of video results within a path response dict"""

ART_PARTIAL_PATHS = [
    ['boxarts', [ART_SIZE_SD, ART_SIZE_FHD, ART_SIZE_POSTER], 'jpg', 'value'],
    ['interestingMoment', [ART_SIZE_SD, ART_SIZE_FHD], 'jpg', 'value'],
    ['artWorkByType', 'LOGO_BRANDED_HORIZONTAL', '_550x124', 'png', 'value'],  # 11/05/2020 same img of bb2OGLogo
    ['storyArt', ART_SIZE_SD, 'jpg', 'value']  # 11/05/2020 same img of BGImages
]

# Old image paths for reference
# ['bb2OGLogo', '_550x124', 'png', 'value']
# ['BGImages', '720', 'jpg', 'value']


VIDEO_LIST_PARTIAL_PATHS = [
    [['requestId', 'summary', 'title', 'synopsis', 'regularSynopsis', 'evidence', 'queue', 'inRemindMeList',
      'episodeCount', 'info', 'maturity', 'runtime', 'seasonCount', 'availability', 'trackIds',
      'releaseYear', 'userRating', 'numSeasonsLabel', 'bookmarkPosition', 'creditsOffset',
      'dpSupplementalMessage', 'watched', 'delivery', 'sequiturEvidence', 'promoVideo', 'availability']],
    [['genres', 'tags', 'creators', 'directors', 'cast'],
     {'from': 0, 'to': 10}, ['id', 'name']]
] + ART_PARTIAL_PATHS

VIDEO_LIST_BASIC_PARTIAL_PATHS = [
    [['title', 'queue', 'watched', 'summary', 'type', 'id']]
]

GENRE_PARTIAL_PATHS = [
    [["id", "requestId", "summary", "name"]],
    [{"from": 0, "to": 48},
     ["context", "displayName", "genreId", "id", "isTallRow", "length",
      "requestId", "type", "videoId"]]
]

SEASONS_PARTIAL_PATHS = [
    ['seasonList', RANGE_PLACEHOLDER, 'summary'],
    ['title']
] + ART_PARTIAL_PATHS

EPISODES_PARTIAL_PATHS = [
    [['requestId', 'summary', 'synopsis', 'regularSynopsis', 'title', 'runtime', 'releaseYear', 'queue',
      'info', 'maturity', 'userRating', 'bookmarkPosition', 'creditsOffset',
      'watched', 'delivery', 'trackIds', 'availability']],
    [['genres', 'tags', 'creators', 'directors', 'cast'],
     {'from': 0, 'to': 10}, ['id', 'name']]
] + ART_PARTIAL_PATHS

TRAILER_PARTIAL_PATHS = [
    [['availability', 'summary', 'synopsis', 'regularSynopsis', 'title', 'trackIds', 'delivery', 'runtime',
      'bookmarkPosition', 'creditsOffset']]
] + ART_PARTIAL_PATHS

EVENT_PATHS = [
    [['requestId', 'title', 'runtime', 'queue', 'bookmarkPosition', 'watched', 'trackIds']]
]

VIDEO_LIST_RATING_THUMB_PATHS = [
    [['summary', 'title', 'userRating', 'trackIds']]
]

SUPPLEMENTAL_TYPE_TRAILERS = 'trailers'

INFO_MAPPINGS = [
    ('Title', ['title', 'value']),  # Title is needed only for UpNext metadata on play method
    ('Year', ['releaseYear', 'value']),
    ('Plot', ['synopsis', 'value']), # 'regularSynopsis' returns english language, website bug  # ['regularSynopsis', 'value']),  # Complete plot
    ('PlotOutline', ['synopsis', 'value']),  # Small plot
    ('Season', ['seasonCount', 'value']),  # Path used with videolist data for 'tvshow' ListItems (get total seasons)
    ('Season', ['summary', 'value', 'shortName']),  # Path used with season list data for 'season' ListItems (get current season)
    ('Season', ['summary', 'value', 'season']),  # Path used with episode list data for 'episode' ListItems (get current season)
    ('Episode', ['episodeCount', 'value']),  # Path used with videolist data for 'tvshow' ListItems (get total episodes)
    ('Episode', ['summary', 'value', 'length']),  # Path used with season list data for 'season' ListItems (get total episodes)
    ('Episode', ['summary', 'value', 'episode']),  # Path used with videolist data for 'tvshow' ListItems (get current episode)
    ('Rating', ['userRating', 'value', 'matchScore']),
    ('UserRating', ['userRating', 'value', 'userRating']),
    ('Mpaa', ['maturity', 'value', 'rating', 'value']),
    ('Duration', ['runtime', 'value']),
    # 'trailer' add the trailer button support to 'Information' window of ListItem, can be used from custom Kodi skins
    #   to reproduce a background promo video when a ListItem is selected
    ('Trailer', ['promoVideo', 'value', 'id']),
    # ListItem.DateAdded: Removed for now, the actual use of this property for tvshow ListItem type is not clear,
    #                     the documentation says "date of adding in the library", but kodi developers say that
    #                     is used as the latest update date
    # ('DateAdded', ['availability', 'value', 'availabilityStartTime'])
]

# pylint: disable=unnecessary-lambda
INFO_TRANSFORMATIONS = {
    'Season': lambda s_value: _convert_season(s_value),
    'Rating': lambda r: r / 10,
    'PlayCount': lambda w: int(w),
    'Trailer': lambda video_id: common.build_url(pathitems=[common.VideoId.SUPPLEMENTAL, str(video_id)],
                                                 mode=G.MODE_PLAY),
    'DateAdded': lambda ats: common.strf_timestamp(int(ats / 1000), '%Y-%m-%d %H:%M:%S')
}

REFERENCE_MAPPINGS = {
    'Cast': 'cast',
    'Director': 'directors',
    'Writer': 'creators',
    'Genre': 'genres'
}


def _convert_season(value):
    if isinstance(value, int):
        return value
    # isdigit is needed to filter out non numeric characters from 'shortName' key
    return int(''.join([n for n in value if n.isdigit()] or '0'))


def build_paths(base_path, partial_paths):
    """Build a list of full paths by concatenating each partial path with the base path"""
    paths = [base_path + partial_path for partial_path in partial_paths]
    return paths


def resolve_refs(references, targets):
    """Return a generator expression that returns the objects in targets
    by resolving the references in sorted order"""
    return (common.get_path(path_ref, targets, include_key=True)
            for index, path_ref in iterate_references(references))


def iterate_references(source):
    """Generator expression that iterates over a dictionary of
    index=>reference pairs (sorted in ascending order by indices) until it
    reaches the first empty reference, which signals the end of the reference
    list.
    Items with a key that do not represent an integer are ignored."""
    for index, ref in sorted({int(k): v
                              for k, v in source.items()
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
                              for k, v in source.items()
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
        f'Unexpected reference format encountered: {ref}'
    )


def _remove_nesting(ref):
    """Remove the outer layer of nesting if ref is a nested reference.
    Return the original reference if it's not nested"""
    return (ref['reference']
            if isinstance(ref, dict) and 'reference' in ref
            else ref)


def jgraph_get(key, data, full_data=None):
    """
    Expand the standard python dict.get() to implement the resolution of Falcor JSON Graph primitive types.
    :param full_data: pass the entire JSON Graph data (is only needed to resolve the 'ref' primitive type),
                      if 'data' is equal to 'full_data' this param can be ignored
    """
    return _resolve_type(data.get(key), full_data or data)


def jgraph_get_path(path, data, full_data=None):
    """
    Retrieve a value from a nested dict by following the path.
    :param full_data: pass the entire JSON Graph data (is only needed to resolve the 'ref' primitive type),
                      if 'data' is equal to 'full_data' this param can be ignored
    :raise KeyError: if any key along the path does not exist
    """
    current_value = jgraph_get(path[0], data, full_data or data)
    if len(path) == 1:
        return current_value
    return jgraph_get_path(path[1:], current_value, full_data or data)


def _resolve_type(return_data, full_data):
    """Resolve the data on basis of Falcor JSON Graph primitive types"""
    if isinstance(return_data, dict):
        primitive_type = return_data.get('$type')
        if primitive_type == 'ref':
            # Reference type: used to find and get a value within the same JSON Graph data
            return_data = jgraph_get_path(return_data['value'], full_data)
            # Look for a recursive reference
            return _resolve_type(return_data, full_data)
        if primitive_type == 'atom':
            # Atom: contains a JSON data and other properties (not managed here) to handle metadata
            return return_data.get('value')
    return return_data


def jgraph_get_list(key, full_data):
    """
    Get the data of a list by resolving the Falcor JSON Graph primitive types
    ('summary' establishes the amount of data to retrieve)
    :return a dict
    """
    data = full_data[key]
    converted = {}
    for n in range(0, jgraph_get_path(['summary', 'length'], data)):
        converted[n] = jgraph_get(str(n), data, full_data)
    return converted


def jgrapgh_len(data_dict):
    """
    Count the values in a JSON Graph dict list of dicts (break counting at first 'atom')
    e.g.
    data_dict = {"0": {"$type": "ref"}, "1": {"$type": "atom"}}
    """
    count = 0
    for value in data_dict:
        if data_dict[value].get('$type') == 'atom':
            break
        count += 1
    return count
