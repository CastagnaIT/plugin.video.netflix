# -*- coding: utf-8 -*-
"""Path info to query the Shakti pathEvaluator"""
from __future__ import unicode_literals

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
     {'from': 0, 'to': 10}, ['id', 'name']],
    [['genres', 'tags', 'creators', 'directors', 'cast'], 'summary']
] + ART_PARTIAL_PATHS

SEASONS_PARTIAL_PATHS = [
    ['seasonList', {'from': 0, 'to': 40}, 'summary'],
] + ART_PARTIAL_PATHS

EPISODES_PARTIAL_PATHS = [
    [['summary', 'synopsis', 'title', 'runtime', 'releaseYear', 'queue',
      'info', 'maturity', 'userRating', 'bookmarkPosition', 'creditOffset',
      'watched', 'delivery']],
    ['genres', {'from': 0, 'to': 1}, ['id', 'name']],
    ['genres', 'summary']
] + ART_PARTIAL_PATHS
