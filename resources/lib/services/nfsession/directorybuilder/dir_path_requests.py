# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2020 Stefano Gottardo (original implementation module)
    Builds and executes PATH requests for the directories

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from typing import TYPE_CHECKING
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from types import SimpleNamespace
import json
import re
import time
import uuid
from urllib.parse import urlencode, urljoin

import requests
import requests.exceptions as req_exceptions

from resources.lib import common
from resources.lib.utils import website
from resources.lib.utils.data_types import (VideoListSorted, SubgenreList, SeasonList, EpisodeList, LoCo, VideoList,
                                            CustomVideoList, LoLoMoCategory, VideoListSupplemental,
                                            VideosList)
from resources.lib.common.exceptions import (InvalidVideoListTypeError, InvalidVideoId, MetadataNotAvailable,
                                             WebsiteParsingError)
from resources.lib.database.db_utils import TABLE_SESSION
from resources.lib.utils.api_paths import (VIDEO_LIST_PARTIAL_PATHS, RANGE_PLACEHOLDER, VIDEO_LIST_BASIC_PARTIAL_PATHS,
                                           SEASONS_PARTIAL_PATHS, EPISODES_PARTIAL_PATHS, ART_PARTIAL_PATHS,
                                           ART_SIZE_FHD, ART_SIZE_POSTER, TRAILER_PARTIAL_PATHS,
                                           SUPPLEMENTAL_TYPE_TRAILERS, build_paths, PATH_REQUEST_SIZE_MAX)
from resources.lib.common import cache_utils
from resources.lib.globals import G
from resources.lib.services.nfsession.session.endpoints import ENDPOINTS
from resources.lib.utils.logging import LOG

GRAPHQL_URL = 'https://web.prod.cloud.netflix.com/graphql'
GRAPHQL_OP_SEASONS = 'dbc3b274-d4f9-4811-aaf1-d082d3b936f2'
GRAPHQL_OP_EPISODES = '27b30e4e-871d-46aa-ac8b-244103d2e37d'
GRAPHQL_OP_SEARCH = '8d902979-56f2-4886-8c16-f8910f6b52ee'
GRAPHQL_OP_CAROUSEL_PAGE = 'cbe70fd8-c3a1-4e1b-9ab3-d690850ad7f3'
GRAPHQL_OP_DETAIL_MODAL = '7265187b-c065-4714-9eee-327751c8e215'
GRAPHQL_OP_DETAIL_MODAL_TRAILERS = '06e30ee5-7983-4fef-8135-5914124b76ad'
TOP_PICKS_SECTION_LABEL = 'top picks'
NETFLIX_TITLE_URL = 'https://www.netflix.com/title/{}'
TITLE_PAGE_GRAPHQL_RE = re.compile(r"netflix\.reactContext\.models\.graphql\s*=\s*JSON\.parse\('(.*?)'\);", re.DOTALL)
TITLE_PAGE_JSONLD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.DOTALL)
LOCO_ROOT_ID_RE = re.compile(r'NES_[A-Za-z0-9_]+_p_\d+')
LOCO_ROOT_CANDIDATE_RE = re.compile(r'NES_[A-Za-z0-9_]+')
LOCO_ROW_RANGE = {'from': 0, 'to': 50}
LOCO_PAGE_RANGE = {'from': 0, 'to': 20}
LOCO_REFERENCE_FIELDS = [
    'availability', 'episodeCount', 'inRemindMeList', 'queue', 'summary',
    'title', 'synopsis', 'runtime', 'seasonCount', 'bookmarkPosition',
    'creditsOffset', 'watched', 'delivery', 'trackIds', 'userRating',
    'maturity', 'releaseYear'
]
LOCO_CATEGORY_CONTEXTS = {
    'comingSoon': ('newThisWeek', 'popularTitles', 'mostWatched', 'trendingNow'),
    'recommendations': ('similars', 'becauseYouAdded', 'becauseYouLiked', 'watchAgain', 'bigRow',
                        'topTen', 'trendingNow', 'popularTitles')
}
SORTED_LIST_CONTEXT_FALLBACKS = {
    ('genres', '1592210'): 'newThisWeek'
}
BROWSER_LOCO_ROW_KEYS = [0, 1, 2, 3, 'continueWatching']
BROWSER_LOCO_OTHER_ROW_KEYS = [1, 2, 3, 'continueWatching']
BROWSER_LOCO_SUMMARY_FIELDS = [
    'availability', 'bbSupplementalMessage', 'bbSupplementalMessageIcon',
    'maturity', 'mostWatchedData', 'summary'
]
BROWSER_LOCO_CURRENT_FIELDS = ['hasAudioDescription', 'summary']
BROWSER_LOCO_CONTINUE_FIELDS = ['bookmarkPosition', 'runtime', 'summary', 'title']
BROWSER_LOCO_REFERENCE_FIELDS = ['availability', 'episodeCount', 'inRemindMeList', 'queue', 'summary']
BROWSER_LOCO_METADATA_FIELDS = BROWSER_LOCO_REFERENCE_FIELDS + [
    'title', 'synopsis', 'runtime', 'seasonCount', 'bookmarkPosition',
    'creditsOffset', 'watched', 'delivery', 'trackIds', 'userRating',
    'maturity', 'releaseYear', 'promoVideo'
]
BROWSER_LOCO_PERSON_FIELDS = ['genres', 'tags', 'creators', 'directors', 'cast']
BROWSER_GENRE_SUBGENRE_FIELDS = ['id', 'name', 'unifiedEntityId']
BROWSER_LOCO_DIRECT_RANGE = {'from': 0, 'to': PATH_REQUEST_SIZE_MAX}
BROWSER_LOCO_HOME_ROW_RANGE = {'from': 4, 'to': 50}
BROWSER_LOCO_HOME_VISIBLE_RANGE = {'from': 0, 'to': 8}
BROWSER_LOCO_CONTINUE_LAZY_RANGE = {'from': 8, 'to': 100}
BROWSER_MYLIST_RANGE = {'from': 0, 'to': 48}
BROWSER_MYLIST_FIELDS = [
    'availability', 'episodeCount', 'inRemindMeList', 'itemSummary',
    'queue', 'summary'
]
SEARCH_GRAPHQL_PAGE_SIZE = 48
SEARCH_TITLE_PAGE_METADATA_LIMIT = SEARCH_GRAPHQL_PAGE_SIZE
SEARCH_TITLE_PAGE_METADATA_WORKERS = 12
METADATA_REFERENCE_KEYS = {
    'cast': ('people', ('cast', 'actors', 'actor', 'starring', 'starringActors')),
    'directors': ('people', ('directors', 'director')),
    'creators': ('people', ('creators', 'creator', 'writers', 'writer')),
    'genres': ('genres', ('genres', 'genre', 'tags'))
}


class _ActiveProfileLinkParser(HTMLParser):
    """Find the profile switch link without exposing its token in logs."""

    def __init__(self, active_profile_guid):
        super().__init__(convert_charrefs=True)
        self.active_profile_guid = str(active_profile_guid or '').lower()
        self.href = None

    def handle_starttag(self, tag, attrs):
        if self.href or tag != 'a' or not self.active_profile_guid:
            return
        attributes = dict(attrs)
        href = attributes.get('href') or ''
        classes = (attributes.get('class') or '').split()
        if self.active_profile_guid in href.lower() and (
                'profile-link' in classes or '/switchprofile' in href.lower()):
            self.href = href


def _value(value):
    return {'value': value}


def _has_reference_entries(item, source):
    refs = item.get(source, {}) if isinstance(item, dict) else {}
    if not isinstance(refs, dict):
        return False
    return any(common.is_numeric(key) for key in refs)


def _metadata_names_from_value(value):
    if not value:
        return []
    if isinstance(value, str):
        return [name.strip() for name in value.split(',') if name.strip()]
    if isinstance(value, list):
        names = []
        for item in value:
            names.extend(_metadata_names_from_value(item))
        return names
    if not isinstance(value, dict):
        return []
    for key in ('name', 'fullName', 'displayName', 'title'):
        name = value.get(key)
        if isinstance(name, str) and name.strip():
            return [name.strip()]
        if isinstance(name, dict):
            nested_names = _metadata_names_from_value(name.get('value') or name)
            if nested_names:
                return nested_names
    for key in ('value', 'person', 'node'):
        nested_names = _metadata_names_from_value(value.get(key))
        if nested_names:
            return nested_names
    if 'edges' in value:
        return _metadata_names_from_value(value.get('edges'))
    if all(common.is_numeric(key) for key in value):
        names = []
        for item in value.values():
            names.extend(_metadata_names_from_value(item))
        return names
    return []


def _metadata_names(metadata, keys):
    names = []
    for key in keys:
        names.extend(_metadata_names_from_value(metadata.get(key)))
    unique_names = []
    seen = set()
    for name in names:
        normalized = name.strip()
        if not normalized or normalized.lower() in seen:
            continue
        seen.add(normalized.lower())
        unique_names.append(normalized)
    return unique_names


def _metadata_has_reference_names(metadata):
    if not isinstance(metadata, dict):
        return False
    for _source, (_target, keys) in METADATA_REFERENCE_KEYS.items():
        if _metadata_names(metadata, keys):
            return True
    return False


def _metadata_has_trailer(metadata):
    return bool(_metadata_trailer_id(metadata) or _metadata_trailer_url(metadata))


def _metadata_year(metadata):
    if not isinstance(metadata, dict):
        return 0
    value = (metadata.get('year') or metadata.get('releaseYear') or
             metadata.get('dateCreated') or metadata.get('datePublished'))
    if isinstance(value, int):
        return value
    match = re.search(r'\b(18|19|20|21)\d{2}\b', str(value or ''))
    return int(match.group(0)) if match else 0


def _title_page_jsonld_data(content):
    from html import unescape
    html_text = content.decode('utf-8', 'replace') if isinstance(content, bytes) else str(content)
    for match in TITLE_PAGE_JSONLD_RE.finditer(html_text):
        try:
            jsonld_data = json.loads(unescape(match.group(1)))
        except (TypeError, ValueError) as exc:
            LOG.debug('Unable to parse title page JSON-LD ({})', type(exc).__name__)
            continue
        candidates = jsonld_data if isinstance(jsonld_data, list) else [jsonld_data]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            if candidate.get('@type') in ('Movie', 'TVSeries') or candidate.get('actors') or candidate.get('creators'):
                return candidate
    return {}


def _metadata_from_title_page(video_id):
    try:
        response = requests.get(
            NETFLIX_TITLE_URL.format(video_id),
            headers={
                'Accept': 'text/html,application/xhtml+xml,application/xml',
                'User-Agent': common.get_user_agent(enable_android_mediaflag_fix=True)
            },
            timeout=8)
        response.raise_for_status()
    except req_exceptions.RequestException as exc:
        LOG.debug('Title page metadata fallback failed for {} ({})', video_id, type(exc).__name__)
        return {}
    return _title_page_jsonld_data(response.content)


def metadata_with_title_page_fallback(video_id, metadata_video=None):
    """Return metadata enriched with public title page JSON-LD fields."""
    metadata_video = dict(metadata_video or {})
    if (_metadata_has_reference_names(metadata_video) and
            _metadata_has_trailer(metadata_video) and
            _metadata_year(metadata_video) and
            (metadata_video.get('synopsis') or metadata_video.get('regularSynopsis'))):
        return metadata_video
    title_page_metadata = _metadata_from_title_page(video_id)
    return _merge_title_page_metadata(metadata_video, title_page_metadata)


def _merge_title_page_metadata(metadata_video, title_page_metadata):
    metadata_video = dict(metadata_video or {})
    if not title_page_metadata:
        return metadata_video
    for key in ('actors', 'directors', 'creators', 'genre', 'trailer'):
        if key in title_page_metadata and key not in metadata_video:
            metadata_video[key] = title_page_metadata[key]
    description = title_page_metadata.get('description')
    if description and not (metadata_video.get('synopsis') or metadata_video.get('regularSynopsis')):
        metadata_video['synopsis'] = description
        metadata_video['regularSynopsis'] = description
    if not _metadata_year(metadata_video):
        title_page_year = _metadata_year(title_page_metadata)
        if title_page_year:
            metadata_video['year'] = title_page_year
    return metadata_video


def _search_title_page_metadata(video_id):
    try:
        response = requests.get(
            NETFLIX_TITLE_URL.format(video_id),
            headers={
                'Accept': 'text/html,application/xhtml+xml,application/xml',
                'User-Agent': common.get_user_agent(enable_android_mediaflag_fix=True)
            },
            timeout=(2, 4))
        response.raise_for_status()
    except req_exceptions.RequestException as exc:
        LOG.debug('Search title page metadata skipped for {} ({})', video_id, type(exc).__name__)
        return {}
    return _title_page_jsonld_data(response.content)


def _metadata_trailer_id(metadata_video):
    promo_video = metadata_video.get('promoVideo')
    if isinstance(promo_video, dict):
        promo_value = promo_video.get('value') if isinstance(promo_video.get('value'), dict) else promo_video
        trailer_id = promo_value.get('id') or promo_value.get('videoId')
        if trailer_id:
            return trailer_id
    trailer_id = metadata_video.get('merchedVideoId') or metadata_video.get('promoVideoId')
    return trailer_id


def _metadata_trailer_url(metadata_video):
    trailer = metadata_video.get('trailer')
    if isinstance(trailer, dict):
        trailer_url = trailer.get('contentUrl') or trailer.get('url')
        if trailer_url:
            return trailer_url
    return metadata_video.get('trailerUrl') or metadata_video.get('previewUrl')


def _add_metadata_trailer(item, metadata_video):
    if item.get('promoVideo') or item.get('trailerUrl'):
        return
    trailer_id = _metadata_trailer_id(metadata_video)
    if trailer_id:
        item['promoVideo'] = _value({'id': trailer_id})
        return
    trailer_url = _metadata_trailer_url(metadata_video)
    if trailer_url:
        item['trailerUrl'] = _value(trailer_url)


def _reference_id(prefix, name, index):
    safe_name = re.sub(r'[^A-Za-z0-9]+', '_', name).strip('_').lower()
    return f'{prefix}_{index}_{safe_name}' if safe_name else f'{prefix}_{index}'


def _add_metadata_references(path_response, item, source, target, names):
    if not names or _has_reference_entries(item, source):
        return
    target_data = path_response.setdefault(target, {})
    refs = item.setdefault(source, {})
    for index, name in enumerate(names[:10]):
        ref_id = _reference_id(f'metadata_{source}', name, index)
        target_data.setdefault(ref_id, {'name': _value(name)})
        refs[str(index)] = {'$type': 'ref', 'value': [target, ref_id]}


def normalize_metadata_references(path_response, video_id, metadata_video, item=None):
    """Copy metadata people/genre fields into the JSON graph reference shape."""
    if not isinstance(metadata_video, dict):
        return
    item = item or path_response.get('videos', {}).get(str(video_id))
    if not isinstance(item, dict):
        return
    for source, (target, keys) in METADATA_REFERENCE_KEYS.items():
        _add_metadata_references(path_response, item, source, target, _metadata_names(metadata_video, keys))
    _add_metadata_trailer(item, metadata_video)


def _summary(video_id, title, video_type, number=None, length=None):
    data = {'id': int(video_id), 'type': video_type, 'name': title}
    if number is not None:
        data['season' if video_type == 'season' else 'episode'] = number
        data['shortName'] = str(number)
    if length is not None:
        data['length'] = length
    return _value(data)


def _graphql_headers():
    headers = {
        'Accept': '*/*',
        'Content-Type': 'application/json',
        'Origin': 'https://www.netflix.com',
        'Referer': 'https://www.netflix.com/browse',
        'x-netflix.nq.stack': 'prod',
        'x-netflix.request.client.user.guid': G.LOCAL_DB.get_active_profile_guid()
    }
    for header, key in (
            ('X-Netflix.browserVersion', 'browser_info_version'),
            ('X-Netflix.osName', 'browser_info_os_name'),
            ('X-Netflix.osVersion', 'browser_info_os_version'),
            ('X-Netflix.uiVersion', 'ui_version')):
        value = G.LOCAL_DB.get_value(key, '', table=('session', ['Name', 'Value']))
        if value:
            headers[header] = value
    return headers


def _season_node_to_item(node, index):
    season_id = str(node['videoId'])
    title = node.get('title') or f'Season {index + 1}'
    episodes = node.get('episodes', {}).get('totalCount')
    return season_id, {
        'summary': _summary(season_id, title, 'season', index + 1, episodes),
        'title': _value(title),
        'availability': _value({'isPlayable': True})
    }


def _episode_node_to_item(node, season_number, metadata=None):
    episode_id = str(node['videoId'])
    metadata = metadata or {}
    synopsis = metadata.get('synopsis') or (node.get('contextualSynopsis') or {}).get('text') or ''
    runtime = metadata.get('runtime') or node.get('runtimeSec') or node.get('displayRuntimeSec') or 0
    bookmark = metadata.get('bookmark') or node.get('bookmark') or {}
    bookmark_position = bookmark.get('offset') or bookmark.get('bookmarkPosition') or 0
    credits_offset = metadata.get('creditsOffset') or metadata.get('watchedToEndOffset') or 0
    watched_threshold = credits_offset - (runtime / 3000 * 50) if credits_offset else runtime * 0.9
    graph_playcount = 1 if 0 < watched_threshold <= bookmark_position else 0
    artwork = node.get('artwork') or {}
    image_url = ''
    if isinstance(artwork, dict):
        image_url = artwork.get('url') or (artwork.get('image') or {}).get('url') or ''
    summary = _summary(episode_id, node.get('title') or '', 'episode', node.get('number'))
    if season_number is not None:
        summary['value']['season'] = season_number
    return episode_id, {
        'summary': summary,
        'title': _value(node.get('title') or ''),
        'synopsis': _value(synopsis),
        'regularSynopsis': _value(synopsis),
        'runtime': _value(runtime),
        'availability': _value({'isPlayable': bool(node.get('isPlayable', True))}),
        'bookmarkPosition': _value(bookmark_position),
        'creditsOffset': _value(metadata.get('creditsOffset', 0)),
        'watchedToEndOffset': _value(metadata.get('watchedToEndOffset', 0)),
        'watched': _value(bool(bookmark.get('watchedDate'))),
        '_graphql_playcount': _value(graph_playcount),
        'interestingMoment': {'_1920x1080': {'jpg': {'value': {'url': image_url}}}},
        'season': _value(season_number)
    }


def _search_graphql_artwork_params():
    return {
        'artworkType': 'BOXSHOT',
        'dimension': {'width': 300, 'height': 420},
        'features': {'fallbackStrategy': 'STILL'}
    }


def _search_graphql_game_artwork_params(artwork_type, top_content_type_badge):
    return {
        'artworkType': artwork_type,
        'dimension': {'width': 342, 'height': 192},
        'features': {'fallbackStrategy': 'STILL', 'topContentTypeBadge': top_content_type_badge}
    }


def _search_graphql_options():
    entity_treatments = {
        'pinotStandardBoxshot': {'base': {'canHandleEntityKinds': ['VIDEO']}},
        'pinotStandardCloudAppIcon': {'base': {'canHandleEntityKinds': ['GAME']}},
        'pinotStandardMobileAppIcon': {'base': {'canHandleEntityKinds': ['GAME']}},
        'pinotStandardDestination': {'base': {'canHandleEntityKinds': ['GENERIC_CONTAINER']}}
    }
    return {
        'pageCapabilities': {'base': {
            'canHandlePlayingCloudGames': False,
            'capabilitiesBySection': {
                'pinotGallery': {'base': {'capabilitiesBySectionTreatment': {
                    'pinotCreatorHome': {'base': {
                        'capabilitiesByEntityTreatment': entity_treatments,
                        'maxTotalEntities': 300
                    }},
                    'pinotStandard': {'base': {
                        'capabilitiesByEntityTreatment': entity_treatments,
                        'maxTotalEntities': 300
                    }}
                }}},
                'pinotList': {'base': {'capabilitiesBySectionTreatment': {
                    'pinotSuggestions': {'base': {
                        'capabilitiesByEntityTreatment': {
                            'pinotSuggestion': {'base': {'canHandleEntityKinds': [
                                'AUTOCOMPLETE', 'VIDEO', 'CHARACTER', 'GENERIC_CONTAINER', 'GENRE', 'PERSON'
                            ]}}
                        },
                        'maxTotalEntities': 100
                    }}
                }}}
            },
            'maxTotalSections': 2
        }},
        'session': {'id': str(uuid.uuid4())}
    }


def _search_graphql_variables(search_term, end_cursor=None):
    return {
        'imageParamsForStandardBoxart': _search_graphql_artwork_params(),
        'imageParamsForCloudGameBoxart': _search_graphql_game_artwork_params(
            'GAME_CLOUD_BOXART_HORIZONTAL_INCOMPATIBLE', True),
        'imageParamsForMobileGameBoxart': _search_graphql_game_artwork_params(
            'GAME_ICON_BOXART_HORIZONTAL_CARD', True),
        'pageSize': SEARCH_GRAPHQL_PAGE_SIZE,
        'options': _search_graphql_options(),
        'searchTerm': search_term,
        'selectedSuggestionId': None,
        'endCursor': end_cursor
    }


def _merge_search_metadata_video(base_video, metadata_video):
    merged = dict(base_video)
    metadata_video = metadata_video or {}
    title = metadata_video.get('title') or merged.get('title', {}).get('value')
    if title:
        merged['title'] = _value(title)
        summary = merged.get('summary', {}).get('value', {})
        if isinstance(summary, dict):
            summary['name'] = title
            merged['summary'] = _value(summary)
    synopsis = metadata_video.get('synopsis') or metadata_video.get('regularSynopsis')
    if synopsis:
        merged['synopsis'] = _value(synopsis)
        merged['regularSynopsis'] = _value(synopsis)
    runtime = metadata_video.get('runtime')
    if runtime:
        merged['runtime'] = _value(runtime)
    release_year = _metadata_year(metadata_video)
    if release_year:
        merged['releaseYear'] = _value(release_year)
    seasons = metadata_video.get('seasons') or []
    if seasons:
        merged['seasonCount'] = _value(len(seasons))
        episode_count = sum(len(season.get('episodes') or []) for season in seasons)
        if episode_count:
            merged['episodeCount'] = _value(episode_count)
    poster_url = _metadata_image_url(metadata_video, ('boxart', 'boxArt'), portrait=True)
    if poster_url:
        boxarts = dict(merged.get('boxarts') or {})
        boxarts[ART_SIZE_POSTER] = {
            'jpg': {'value': {'url': poster_url}}
        }
        merged['boxarts'] = boxarts
    landscape_url = _metadata_image_url(
        metadata_video, ('artwork', 'storyart', 'storyArt', 'stills'), portrait=False)
    if landscape_url:
        interesting_moments = dict(merged.get('interestingMoment') or {})
        interesting_moments[ART_SIZE_FHD] = {
            'jpg': {'value': {'url': landscape_url}}
        }
        merged['interestingMoment'] = interesting_moments
    return merged


def _metadata_video_to_item(video_id, metadata_video):
    title = metadata_video.get('title') or str(video_id)
    video_type = str(metadata_video.get('type') or metadata_video.get('videoType') or '').lower()
    if video_type not in ('movie', 'show'):
        video_type = 'show' if metadata_video.get('seasons') else 'movie'
    base_video = {
        'summary': _summary(str(video_id), title, video_type),
        'title': _value(title),
        'availability': _value({'isPlayable': True}),
        'queue': _value({'inQueue': False}),
        'inRemindMeList': _value(False),
        'bookmarkPosition': _value(0),
        'creditsOffset': _value(0),
        'watchedToEndOffset': _value(0),
        'watched': _value(False),
        'runtime': _value(0),
        'releaseYear': _value(0),
        'maturity': _value({}),
        'trackIds': _value({}),
        'requestId': _value('')
    }
    return _merge_search_metadata_video(base_video, metadata_video)


def _metadata_image_url(metadata, keys, portrait):
    candidates = []

    def _collect(value):
        if isinstance(value, str):
            if value.startswith('http'):
                candidates.append((value, 0, 0))
            return
        if isinstance(value, list):
            for item in value:
                _collect(item)
            return
        if not isinstance(value, dict):
            return
        url = value.get('url')
        if isinstance(url, str) and url.startswith('http'):
            width = value.get('w') or value.get('width') or 0
            height = value.get('h') or value.get('height') or 0
            candidates.append((url, width, height))
        else:
            for nested_value in value.values():
                _collect(nested_value)

    for key in keys:
        _collect(metadata.get(key) if isinstance(metadata, dict) else None)
    if not candidates:
        return ''
    matching = [
        candidate for candidate in candidates
        if candidate[1] and candidate[2] and
        ((candidate[2] > candidate[1]) if portrait else (candidate[1] > candidate[2]))
    ]
    if matching:
        return max(matching, key=lambda candidate: candidate[1] * candidate[2])[0]
    unknown_size = [candidate for candidate in candidates if not candidate[1] or not candidate[2]]
    return unknown_size[0][0] if unknown_size else ''


def _search_graphql_node_to_item(node):
    entity = node.get('unifiedEntity') or {}
    entity_type = entity.get('__typename')
    if entity_type not in ('Movie', 'Show'):
        return None
    video_id = str(entity.get('videoId') or '')
    if not video_id:
        return None
    video_type = 'movie' if entity_type == 'Movie' else 'show'
    title = node.get('displayString') or str(video_id)
    item = {
        'summary': _summary(video_id, title, video_type),
        'title': _value(title),
        'availability': _value({'isPlayable': True}),
        'queue': _value({'inQueue': False}),
        'inRemindMeList': _value(False),
        'bookmarkPosition': _value(0),
        'creditsOffset': _value(0),
        'watchedToEndOffset': _value(0),
        'watched': _value(False),
        'runtime': _value(entity.get('runtimeSec', 0)),
        'releaseYear': _value(entity.get('releaseYear', 0)),
        'maturity': _value(entity.get('contentAdvisory') or {}),
        'trackIds': _value({}),
        'requestId': _value('')
    }
    artwork = (node.get('contextualArtwork') or {}).get('artwork') or {}
    if artwork.get('url'):
        _set_browser_boxart(item, {
            'id': int(video_id),
            'title': title,
            'boxArt': {
                'url': artwork['url'],
                'width': artwork.get('width') or artwork.get('w'),
                'height': artwork.get('height') or artwork.get('h')
            }
        })
    return video_id, item


def _carousel_graphql_variables(row_id, end_cursor):
    return {
        'rowId': row_id,
        'carouselAfterCursor': end_cursor,
        'carouselPageSize': 12,
        'eddEnabled': False,
        'imageParamsForStandardBoxart': {
            'artworkType': 'SDP',
            'dimension': {'width': 342, 'height': 192},
            'features': {'fallbackStrategy': 'STILL'}
        },
        'imageParamsForRankedBoxart': {
            'artworkType': 'BOXSHOT',
            'dimension': {'width': 426, 'height': 607},
            'features': {'fallbackStrategy': 'STILL', 'suppressTop10Badge': True}
        },
        'imageParamsForContinueWatchingBoxart': {
            'artworkType': 'SDP',
            'dimension': {'width': 342, 'height': 192},
            'features': {'fallbackStrategy': 'STILL'}
        },
        'imageParamsForMobileGameBoxart': {
            'artworkType': 'APP_ICON',
            'dimension': {'width': 200, 'height': 200},
            'formats': ['WEBP', 'JPG', 'PNG']
        },
        'imageParamsForCloudGameBoxart': {
            'artworkType': 'SDP',
            'dimension': {'width': 342, 'height': 192},
            'features': {'fallbackStrategy': 'STILL'}
        },
        'imageParamsForCharacterCircle': {
            'artworkType': 'SQUAREHEADSHOT_1000x1000',
            'dimension': {'width': 200, 'height': 200},
            'formats': ['WEBP', 'JPG', 'PNG']
        },
        'carouselVersion': '1'
    }



def _graphql_cache_node(graphql_data, typename, video_id):
    video_id = str(video_id)
    direct_key = f'{typename}:{{"videoId":{video_id}}}'
    node = graphql_data.get(direct_key)
    if isinstance(node, dict):
        return node
    key_prefix = f'{typename}:'
    for key, candidate in graphql_data.items():
        if not isinstance(candidate, dict):
            continue
        if key.startswith(key_prefix) and str(candidate.get('videoId')) == video_id:
            return candidate
    return None


def _graphql_ref_node(graphql_data, node_or_ref):
    if not isinstance(node_or_ref, dict):
        return None
    ref = node_or_ref.get('__ref')
    if ref:
        return graphql_data.get(ref)
    return node_or_ref


def _iter_graphql_edges(value):
    if isinstance(value, dict) and '__ref' in value:
        return []
    edges = value.get('edges') if isinstance(value, dict) else value
    if isinstance(edges, dict):
        return edges.values()
    if isinstance(edges, list):
        return edges
    return []


def _first_artwork_url(value):
    if isinstance(value, dict):
        url = value.get('url')
        if isinstance(url, str) and url.startswith('http'):
            return url
        for nested in value.values():
            nested_url = _first_artwork_url(nested)
            if nested_url:
                return nested_url
    elif isinstance(value, list):
        for nested in value:
            nested_url = _first_artwork_url(nested)
            if nested_url:
                return nested_url
    return ''


def _supplemental_artwork_url(node):
    for key, value in node.items():
        if not any(name in key.lower() for name in ('artwork', 'boxart', 'storyart', 'still')):
            continue
        image_url = _first_artwork_url(value)
        if image_url:
            return image_url
    return ''


def _supplemental_node_to_item(node):
    video_id = str(node.get('videoId') or node.get('id') or '')
    # DetailModalTrailers is authoritative for collection playability. Do not
    # turn an explicitly unplayable (or incomplete) card into a playable Kodi
    # item merely because it has a video id.
    if not video_id or node.get('isPlayable') is not True:
        return None
    title = node.get('title') or node.get('displayName') or video_id
    item = {
        'summary': _summary(video_id, title, 'movie'),
        'title': _value(title),
        'availability': _value({'isPlayable': True}),
        'queue': _value({'inQueue': False}),
        'inRemindMeList': _value(False),
        'bookmarkPosition': _value(0),
        'creditsOffset': _value(0),
        'watchedToEndOffset': _value(0),
        'watched': _value(False),
        'runtime': _value(node.get('displayRuntimeSec') or node.get('runtimeSec') or node.get('runtime') or 0),
        'trackIds': _value({'trackId': video_id}),
        'requestId': _value('')
    }
    synopsis = node.get('synopsis') or node.get('contextualSynopsis') or ''
    if isinstance(synopsis, dict):
        synopsis = synopsis.get('text') or synopsis.get('value') or ''
    if synopsis:
        item['synopsis'] = _value(synopsis)
        item['regularSynopsis'] = _value(synopsis)
    image_url = _supplemental_artwork_url(node)
    if image_url:
        _set_browser_boxart(item, {'id': int(video_id), 'title': title, 'boxArt': {'url': image_url}})
    return video_id, item


def _supplemental_videos_from_graphql_cache(graphql_data, video_id):
    if not isinstance(graphql_data, dict):
        return OrderedDict()
    title_node = (_graphql_cache_node(graphql_data, 'Show', video_id) or
                  _graphql_cache_node(graphql_data, 'Movie', video_id))
    if not isinstance(title_node, dict):
        return OrderedDict()
    supplemental_list = title_node.get('supplementalVideosList') or {}
    supplemental_list = _graphql_ref_node(graphql_data, supplemental_list) or supplemental_list
    videos = OrderedDict()
    for edge in _iter_graphql_edges(supplemental_list):
        edge_node = edge.get('node') if isinstance(edge, dict) else edge
        supplemental_node = _graphql_ref_node(graphql_data, edge_node)
        if not isinstance(supplemental_node, dict):
            continue
        item = _supplemental_node_to_item(supplemental_node)
        if item:
            videos[item[0]] = item[1]
    return videos


def _title_page_graphql_data(content, react_context):
    graphql_data = common.get_path_safe(['models', 'graphql', 'data'], react_context, False, {})
    if isinstance(graphql_data, dict) and graphql_data:
        return graphql_data
    html = content.decode('utf-8', 'replace') if isinstance(content, bytes) else str(content)
    match = TITLE_PAGE_GRAPHQL_RE.search(html)
    if not match:
        return {}
    try:
        graphql_cache = json.loads(website.decode_javascript_string(match.group(1)))
    except (TypeError, ValueError, UnicodeDecodeError) as exc:
        LOG.warn('Unable to parse title page GraphQL cache ({})', type(exc).__name__)
        return {}
    graphql_data = graphql_cache.get('data') if isinstance(graphql_cache, dict) else None
    return graphql_data if isinstance(graphql_data, dict) else {}


def _normalize_browser_list_lengths(path_response):
    for list_data in path_response.get('lists', {}).values():
        if not isinstance(list_data, dict):
            continue
        length = list_data.get('componentSummary', {}).get('value', {}).get('length')
        if not isinstance(length, int):
            continue
        for key in list(list_data.keys()):
            if common.is_numeric(key) and int(key) >= length:
                del list_data[key]


def _browser_reference_paths(reference_path, include_metadata=False):
    fields = BROWSER_LOCO_METADATA_FIELDS if include_metadata else BROWSER_LOCO_REFERENCE_FIELDS
    paths = [reference_path + [fields]]
    if include_metadata:
        paths.append(reference_path + [BROWSER_LOCO_PERSON_FIELDS, {'from': 0, 'to': 10}, ['id', 'name']])
    return paths


def _boxart_dimensions(boxart):
    try:
        width = int(boxart.get('width') or boxart.get('w') or 0)
        height = int(boxart.get('height') or boxart.get('h') or 0)
    except (TypeError, ValueError):
        return 0, 0
    return width, height


def _set_browser_boxart(video, item_summary):
    boxart = item_summary.get('boxArt') or {}
    image_url = boxart.get('url')
    width, height = _boxart_dimensions(boxart)
    is_portrait = bool(width and height and height > width)
    item_summary_value = dict(item_summary)
    if image_url and not is_portrait:
        item_summary_value.pop('boxArt', None)
    video['itemSummary'] = _value(item_summary_value)
    if not image_url:
        return
    art_value = {'url': image_url}
    if is_portrait:
        video.setdefault('boxarts', {})
        video['boxarts'].setdefault(ART_SIZE_POSTER, {'jpg': {'value': art_value}})
    else:
        video.setdefault('interestingMoment', {})
        video['interestingMoment'].setdefault(ART_SIZE_FHD, {'jpg': {'value': art_value}})


def _browser_item_summary_score(item_summary):
    synopses = item_summary.get('synopses') or {}
    synopsis = (synopses.get('regularSynopsis') or synopses.get('shortSynopsis') or
                synopses.get('narrative'))
    return bool(synopsis), len(synopsis or ''), len(item_summary)


def _normalize_browser_video_fields(path_response):
    _normalize_browser_list_lengths(path_response)
    item_summaries = {}
    for list_data in path_response.get('lists', {}).values():
        if not isinstance(list_data, dict):
            continue
        for item in list_data.values():
            if not isinstance(item, dict):
                continue
            item_summary = item.get('itemSummary', {}).get('value', {})
            ref = item.get('reference', {})
            ref_value = ref.get('value') if isinstance(ref, dict) else ref
            if isinstance(ref_value, dict) and 'value' in ref_value:
                ref_value = ref_value['value']
            if isinstance(ref_value, list) and len(ref_value) >= 2 and ref_value[0] == 'videos':
                video_id = str(ref_value[1])
                current_summary = item_summaries.get(video_id, {})
                if _browser_item_summary_score(item_summary) > _browser_item_summary_score(current_summary):
                    item_summaries[video_id] = item_summary
    for video_id, video in path_response.get('videos', {}).items():
        if not isinstance(video, dict):
            continue
        item_summary = item_summaries.get(str(video_id), {})
        if not item_summary:
            item_summary = video.get('itemSummary', {}).get('value', {})
        if item_summary:
            video.setdefault('itemSummary', _value(item_summary))
            _set_browser_boxart(video, item_summary)
        current = video.get('current', {})
        if isinstance(current, dict):
            for key in BROWSER_LOCO_CONTINUE_FIELDS:
                if key in current and key not in video:
                    video[key] = current[key]
        summary = video.get('summary', {}).get('value', {})
        if not isinstance(summary, dict):
            summary = {}
        title_data = video.get('title')
        title_value = title_data.get('value') if isinstance(title_data, dict) else title_data
        if not title_value:
            nested_title = summary.get('title')
            if isinstance(nested_title, dict):
                title_value = nested_title.get('value')
            elif nested_title:
                title_value = nested_title
            else:
                title_value = (item_summary.get('title') or item_summary.get('name') or
                               item_summary.get('displayName') or summary.get('name') or str(video_id))
            video['title'] = _value(title_value)
        if title_value and isinstance(summary, dict):
            summary.setdefault('name', title_value)
        synopses = item_summary.get('synopses') or {}
        synopsis = synopses.get('regularSynopsis') or synopses.get('shortSynopsis') or synopses.get('narrative')
        if synopsis:
            video.setdefault('synopsis', _value(synopsis))
            video.setdefault('regularSynopsis', _value(synopsis))
        video.setdefault('availability', _value(item_summary.get('availability', {'isPlayable': True})))
        video.setdefault('queue', _value({'inQueue': False}))
        video.setdefault('inRemindMeList', _value(False))
        video.setdefault('bookmarkPosition', _value(0))
        video.setdefault('creditsOffset', _value(0))
        video.setdefault('watchedToEndOffset', _value(0))
        video.setdefault('watched', _value(False))
        video.setdefault('runtime', _value(summary.get('runtime', item_summary.get('runtime', item_summary.get('infoDensityRuntime', 0)))))
        video.setdefault('releaseYear', _value(item_summary.get('releaseYear', 0)))
        video.setdefault('seasonCount', _value(item_summary.get('seasonCount', 0)))
        video.setdefault('episodeCount', _value(item_summary.get('episodeCount', 0)))
        video.setdefault('maturity', _value(item_summary.get('maturity', {})))
        video.setdefault('trackIds', _value({}))
        video.setdefault('requestId', _value(item_summary.get('requestId', '')))


def _browser_list_video_ids(path_response, list_id):
    video_ids = []
    list_data = path_response.get('lists', {}).get(str(list_id), {})
    for key, item in list_data.items():
        if not common.is_numeric(key) or not isinstance(item, dict):
            continue
        ref = item.get('reference', {})
        ref_value = ref.get('value') if isinstance(ref, dict) else ref
        if isinstance(ref_value, dict) and 'value' in ref_value:
            ref_value = ref_value['value']
        video_id = None
        if isinstance(ref_value, list) and len(ref_value) >= 2 and ref_value[0] == 'videos':
            video_id = ref_value[1]
        if video_id is None:
            video_id = item.get('itemSummary', {}).get('value', {}).get('videoId')
        if video_id is not None and str(video_id) not in video_ids:
            video_ids.append(str(video_id))
    return video_ids

if TYPE_CHECKING:  # This variable/imports are used only by the editor, so not at runtime
    from resources.lib.services.nfsession.nfsession_ops import NFSessionOperations


class DirectoryPathRequests:
    """Builds and executes PATH requests for the directories"""

    def __init__(self, nfsession: 'NFSessionOperations'):
        self.nfsession = nfsession

    @cache_utils.cache_output(cache_utils.CACHE_MYLIST, fixed_identifier='my_list_items', ignore_self_class=True)
    def req_mylist_items(self):
        """Return the 'my list' video list as videoid items"""
        LOG.debug('Requesting "my list" video list as videoid items')
        try:
            video_list = self._browser_mylist_video_list()
            if video_list:
                return [common.VideoId.from_videolist_item(video)
                        for video in video_list.videos.values()]
        except InvalidVideoListTypeError:
            return []
        except req_exceptions.HTTPError as exc:
            if getattr(exc.response, 'status_code', None) != 404:
                raise
            LOG.warn('My List marker lookup disabled because pathEvaluator returned 404')
        return []

    @cache_utils.cache_output(cache_utils.CACHE_COMMON, fixed_identifier='loco_list', ignore_self_class=True)
    def req_loco_list_root(self):
        """Retrieve root LoCo list"""
        # It is used to following cases:
        # - To get items for the main menu
        #      (when 'loco_known'==True and loco_contexts is set, see MAIN_MENU_ITEMS in globals.py)
        # - To get list items for menus that have multiple contexts set to 'loco_contexts' like 'recommendations' menu
        LOG.debug('Requesting LoCo root lists')
        paths = ([['loco', 'componentSummary'],
                  ['loco', {'from': 0, 'to': 50}, 'componentSummary'],
                  # Titles of first 4 videos in each video list (needed only to show titles in the plot description)
                  ['loco', {'from': 0, 'to': 50}, {'from': 0, 'to': 3}, 'reference', ['title', 'summary']]] +
                 # Art for the first video of each context list (needed only to add art to the menu item)
                 build_paths(['loco', {'from': 0, 'to': 50}, 0, 'reference'], ART_PARTIAL_PATHS))
        call_args = {'paths': paths}
        try:
            path_response = self.nfsession.path_request(**call_args)
        except req_exceptions.HTTPError as exc:
            if exc.response is None or exc.response.status_code != 404:
                raise
            LOG.warn('Falling back to empty LoCo root menu after pathEvaluator 404')
            path_response = {'locos': {'root': {'componentSummary': _value({'length': 0})}}, 'lists': {}}
        return LoCo(path_response)

    @cache_utils.cache_output(cache_utils.CACHE_GENRES, identify_from_kwarg_name='genre_id', ignore_self_class=True)
    def req_loco_list_genre(self, genre_id):
        """Retrieve LoCo for the given genre"""
        LOG.debug('Requesting LoCo for genre {}', genre_id)
        return self._req_browser_genre_loco(genre_id)

    def get_loco_list_id_by_context(self, context):
        """Return the dynamic video list ID for a LoCo context"""
        try:
            return next(iter(self.req_loco_list_root().lists_by_context([context], True)))[0]
        except StopIteration as exc:
            raise InvalidVideoListTypeError(f'No lists with context {context} available') from exc

    @cache_utils.cache_output(cache_utils.CACHE_COMMON, fixed_identifier='profiles_raw_data',
                              ttl=300, ignore_self_class=True)
    def req_profiles_info(self, update_database=True):
        """Retrieve raw data of the profiles (and save it to the database)"""
        paths = ([['profilesList', 'summary'],
                  ['profilesList', 'current', 'summary'],
                  ['profilesList', {'to': 5}, 'summary'],
                  ['profilesList', {'to': 5}, 'avatar', 'images', 'byWidth', 320]])
        path_response = self.nfsession.path_request(paths)
        if update_database:
            from resources.lib.utils.website import parse_profiles
            parse_profiles(path_response)
        return path_response

    @cache_utils.cache_output(cache_utils.CACHE_COMMON, identify_append_from_kwarg_name='perpetual_range_start',
                              ignore_self_class=True)
    def req_seasons(self, videoid, perpetual_range_start):
        """Retrieve the seasons of a tv show"""
        if videoid.mediatype != common.VideoId.SHOW:
            raise InvalidVideoId(f'Cannot request season list for {videoid}')
        LOG.debug('Requesting the seasons list for show {}', videoid)
        call_args = {
            'paths': (build_paths(['videos', videoid.tvshowid], SEASONS_PARTIAL_PATHS) +
                      build_paths(['videos', videoid.tvshowid], ART_PARTIAL_PATHS) +
                      [['videos', videoid.tvshowid, 'componentSummary']]),
            'length_params': ['stdlist_wid', ['videos', videoid.tvshowid, 'seasonList']],
            'perpetual_range_start': perpetual_range_start
        }
        try:
            path_response = self.nfsession.perpetual_path_request(**call_args)
            return SeasonList(videoid, path_response)
        except req_exceptions.HTTPError as exc:
            if getattr(exc.response, 'status_code', None) != 404:
                raise
            LOG.warn('Falling back to GraphQL season selector for show {}', videoid.tvshowid)
            return self._req_seasons_graphql(videoid)

    @cache_utils.cache_output(cache_utils.CACHE_COMMON, identify_from_kwarg_name='videoid',
                              identify_append_from_kwarg_name='perpetual_range_start', ignore_self_class=True)
    def req_episodes(self, videoid, perpetual_range_start=None):
        """Retrieve the episodes of a season"""
        if videoid.mediatype != common.VideoId.SEASON:
            raise InvalidVideoId(f'Cannot request episode list for {videoid}')
        LOG.debug('Requesting episode list for {}', videoid)
        paths = ([['seasons', videoid.seasonid, 'summary']] +
                 [['seasons', videoid.seasonid, 'componentSummary']] +
                 build_paths(['seasons', videoid.seasonid, 'episodes', RANGE_PLACEHOLDER], EPISODES_PARTIAL_PATHS) +
                 build_paths(['videos', videoid.tvshowid], ART_PARTIAL_PATHS + [[['title', 'delivery']]]))
        call_args = {
            'paths': paths,
            'length_params': ['stdlist_wid', ['seasons', videoid.seasonid, 'episodes']],
            'perpetual_range_start': perpetual_range_start
        }
        try:
            path_response = self.nfsession.perpetual_path_request(**call_args)
            return EpisodeList(videoid, path_response)
        except req_exceptions.HTTPError as exc:
            if getattr(exc.response, 'status_code', None) != 404:
                raise
            LOG.warn('Falling back to GraphQL episode selector for season {}', videoid.seasonid)
            return self._req_episodes_graphql(videoid)

    def _post_graphql(self, operation_name, variables, operation_id):
        payload = {
            'operationName': operation_name,
            'variables': variables,
            'extensions': {'persistedQuery': {'id': operation_id, 'version': 102}}
        }
        response = self.nfsession.session.post(
            GRAPHQL_URL,
            json=payload,
            headers=_graphql_headers(),
            timeout=8)
        response.raise_for_status()
        return response.json()['data']

    def _req_seasons_graphql(self, videoid):
        data = self._post_graphql(
            'PreviewModalEpisodeSelector',
            {'showId': int(videoid.tvshowid), 'seasonCount': 50},
            GRAPHQL_OP_SEASONS)
        show_data = data['videos'][0]
        edges = show_data['seasons']['edges']
        seasons = OrderedDict(
            _season_node_to_item(edge.get('node') or edge, index)
            for index, edge in enumerate(edges))
        show_title = self._metadata_show_title(videoid) or show_data.get('title') or str(videoid.tvshowid)
        tvshow = {
            'title': _value(show_title),
            'delivery': _value({}),
            'seasonList': {'summary': _value({'length': len(seasons)})}
        }
        return SimpleNamespace(
            perpetual_range_selector=None,
            data={'videos': {videoid.tvshowid: tvshow}, 'seasons': seasons},
            videoid=videoid,
            artitem=tvshow,
            tvshow=tvshow,
            seasons=seasons)

    def _metadata_show_title(self, videoid):
        try:
            metadata_data = self.nfsession.get_safe(
                endpoint='metadata',
                params={'movieid': videoid.tvshowid, '_': int(time.time() * 1000)})
            return metadata_data['video'].get('title') or ''
        except (MetadataNotAvailable, KeyError, TypeError, req_exceptions.RequestException):
            return ''

    def _metadata_episodes_by_id(self, videoid):
        try:
            metadata_data = self.nfsession.get_safe(
                endpoint='metadata',
                params={'movieid': videoid.tvshowid, '_': int(time.time() * 1000)})
            show_metadata = metadata_data['video']
        except (MetadataNotAvailable, KeyError, TypeError, req_exceptions.RequestException):
            return {}
        episodes = {}
        for season in show_metadata.get('seasons', []):
            if str(season.get('id')) != videoid.seasonid:
                continue
            for episode in season.get('episodes', []):
                episodes[str(episode.get('id'))] = episode
            break
        return episodes


    def _req_episodes_graphql(self, videoid):
        data = self._post_graphql(
            'PreviewModalEpisodeSelectorSeasonEpisodes',
            {
                'seasonId': int(videoid.seasonid),
                'count': 50,
                'opaqueImageFormat': 'JPG',
                'artworkContext': {}
            },
            GRAPHQL_OP_EPISODES)
        season_data = data['videos'][0]
        season_number = season_data.get('number')
        edges = season_data['episodes']['edges']
        metadata_by_id = self._metadata_episodes_by_id(videoid)
        episodes = OrderedDict(
            _episode_node_to_item(edge.get('node') or edge, season_number,
                                  metadata_by_id.get(str((edge.get('node') or edge).get('videoId'))))
            for edge in edges)
        show_title = self._metadata_show_title(videoid) or str(videoid.tvshowid)
        tvshow = {
            'title': _value(show_title),
            'delivery': _value({})
        }
        season = {
            'summary': _summary(videoid.seasonid, season_data.get('title') or '', 'season', season_number, len(episodes)),
            'title': _value(season_data.get('title') or '')
        }
        path_response = {'videos': {videoid.tvshowid: tvshow}, 'seasons': {videoid.seasonid: season},
                         'episodes': episodes}
        for episode_id, episode in episodes.items():
            normalize_metadata_references(path_response, episode_id, metadata_by_id.get(str(episode_id)), episode)
        return SimpleNamespace(
            perpetual_range_selector=None,
            data=path_response,
            videoid=videoid,
            tvshow=tvshow,
            season=season,
            episodes=episodes)

    def _browse_html_and_auth_url(self):
        browse_html = self.nfsession.get_safe('browse')
        api_data = self.nfsession.website_extract_session_data(browse_html)
        self.nfsession.auth_url = api_data['auth_url']
        browse_text = browse_html.decode('utf-8', 'replace') if isinstance(browse_html, bytes) else browse_html
        return browse_text, api_data['auth_url']

    def _get_current_loco_root_id(self):
        browse_html, auth_url = self._browse_html_and_auth_url()
        match = LOCO_ROOT_ID_RE.search(browse_html)
        if match:
            return match.group(0), auth_url
        root_id = self._probe_current_loco_root_id(self._loco_root_candidates(browse_html), auth_url)
        if not root_id:
            raise InvalidVideoListTypeError('No current LoCo root id found in browse page')
        return root_id, auth_url

    def _loco_root_candidates(self, browse_html):
        seen = set()
        for match in LOCO_ROOT_CANDIDATE_RE.finditer(browse_html):
            candidate = match.group(0)
            if candidate in seen:
                continue
            seen.add(candidate)
            yield candidate

    def _probe_current_loco_root_id(self, candidates, auth_url):
        for candidate in candidates:
            try:
                path_response = self._post_current_loco_paths(
                    [['locos', candidate, 'componentSummary']], auth_url)
            except req_exceptions.RequestException:
                continue
            root_data = path_response.get('locos', {}).get(candidate)
            if isinstance(root_data, dict) and root_data.get('componentSummary', {}).get('value'):
                LOG.warn('Using probed current LoCo root candidate from browse page')
                return candidate
        return None

    def _current_loco_paths(self, root_id):
        return ([
            ['locos', root_id, 'componentSummary'],
            ['locos', root_id, LOCO_ROW_RANGE, 'componentSummary'],
            ['locos', root_id, LOCO_ROW_RANGE, 'page', 0, LOCO_PAGE_RANGE, 'itemSummary'],
            ['locos', root_id, LOCO_ROW_RANGE, 'page', 0, LOCO_PAGE_RANGE, 'reference', LOCO_REFERENCE_FIELDS]
        ] + build_paths(
            ['locos', root_id, LOCO_ROW_RANGE, 'page', 0, LOCO_PAGE_RANGE, 'reference'],
            ART_PARTIAL_PATHS))

    def _post_current_loco_paths(self, paths, auth_url):
        self.nfsession.auth_url = auth_url
        return self._post_browser_path_evaluator(paths, 'https://www.netflix.com/browse')

    def _post_browser_path_evaluator_with_fallback(self, paths, fallback_paths, referer, description):
        try:
            return self._post_browser_path_evaluator(paths, referer)
        except req_exceptions.HTTPError as exc:
            status_code = getattr(exc.response, 'status_code', None)
            if status_code not in (404, 412):
                raise
            LOG.warn('{} metadata fields request returned {}; retrying light fields',
                     description, status_code)
            return self._post_browser_path_evaluator(fallback_paths, referer)

    def _post_browser_path_evaluator(self, paths, referer):
        api_url = G.LOCAL_DB.get_value(
            'api_endpoint_url',
            'https://www.netflix.com/nq/website/memberapi/release',
            table=TABLE_SESSION)
        form_data = [('path', json.dumps(path, separators=(',', ':'))) for path in paths]
        form_data.append(('authURL', self.nfsession.auth_url))
        response = self.nfsession.session.post(
            f'{api_url}/pathEvaluator',
            params={
                'webp': 'false',
                'drmSystem': 'widevine',
                'isVolatileBillboardsEnabled': 'true',
                'isTop10Supported': 'true',
                'hasVideoMerchInBob': 'false',
                'hasVideoMerchInJaw': 'false',
                'falcor_server': '0.1.0',
                'withSize': 'true',
                'materialize': 'true',
                'original_path': '/shakti/mre/pathEvaluator'
            },
            data=urlencode(form_data),
            headers={
                'Accept': '*/*',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://www.netflix.com',
                'Referer': referer,
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-origin',
                'x-netflix.nq.stack': 'prod',
                'x-netflix.request.client.context': 'www.netflix.com',
                'x-netflix.request.client.user.guid': G.LOCAL_DB.get_active_profile_guid()
            },
            timeout=8)
        response.raise_for_status()
        path_response = response.json()['jsonGraph']
        _normalize_browser_video_fields(path_response)
        return path_response

    def _browser_loco_paths(self, root_path, include_genre_paths=False, include_full_rows=False,
                            include_metadata=False):
        paths = [
            root_path + [['componentSummary', 'debugRequest']],
            root_path + [BROWSER_LOCO_ROW_KEYS, 'componentSummary'],
            root_path + ['meta', ['responseExpiration', 'statusCode']],
            root_path + [0, 0, 'itemSummary'],
            root_path + [0, 0, 'reference', BROWSER_LOCO_SUMMARY_FIELDS],
            root_path + [0, 0, 'reference', 'current', BROWSER_LOCO_CURRENT_FIELDS],
            root_path + [0, 'page', 0, LOCO_PAGE_RANGE, 'itemSummary'],
            root_path + [BROWSER_LOCO_OTHER_ROW_KEYS, 'page', 0, LOCO_PAGE_RANGE, 'itemSummary'],
            root_path + ['continueWatching', 'page', 0, LOCO_PAGE_RANGE, 'reference', 'current',
                         BROWSER_LOCO_CONTINUE_FIELDS]
        ]
        paths.extend(_browser_reference_paths(
            root_path + [BROWSER_LOCO_ROW_KEYS, 'page', 0, LOCO_PAGE_RANGE, 'reference']))
        if include_full_rows:
            paths.append(root_path + [BROWSER_LOCO_ROW_KEYS, BROWSER_LOCO_DIRECT_RANGE, 'itemSummary'])
            paths.extend(_browser_reference_paths(
                root_path + [BROWSER_LOCO_ROW_KEYS, BROWSER_LOCO_DIRECT_RANGE, 'reference'],
                include_metadata=include_metadata))
        if include_genre_paths:
            paths.insert(0, root_path[:-1] + [['name', 'trackIds']])
        return paths

    def _browser_video_list_paths(self, list_id, include_metadata=False):
        paths = [
            ['lists', list_id, ['componentSummary', 'debugRequest']],
            ['lists', list_id, 'page', 0, LOCO_PAGE_RANGE, 'itemSummary']
        ]
        paths.extend(_browser_reference_paths(['lists', list_id, 'page', 0, LOCO_PAGE_RANGE, 'reference'],
                                              include_metadata=include_metadata))
        return paths

    def _browser_video_list_full_paths(self, list_id, include_metadata=False):
        paths = [
            ['lists', list_id, ['componentSummary', 'debugRequest']],
            ['lists', list_id, BROWSER_LOCO_DIRECT_RANGE, 'itemSummary']
        ]
        paths.extend(_browser_reference_paths(['lists', list_id, BROWSER_LOCO_DIRECT_RANGE, 'reference'],
                                              include_metadata=include_metadata))
        return paths

    def _req_browser_lolomo_category(self, category_name):
        self._browse_html_and_auth_url()
        path_response = self._post_browser_path_evaluator(
            self._browser_loco_paths(['lolomoByCategory', category_name]),
            'https://www.netflix.com/latest')
        return LoLoMoCategory(path_response)

    def _req_browser_genre_loco(self, genre_id):
        self._browse_html_and_auth_url()
        path_response = self._post_browser_path_evaluator(
            self._browser_loco_paths(['genres', int(genre_id), 'rw'], include_genre_paths=True),
            f'https://www.netflix.com/browse/genre/{genre_id}')
        return LoCo(path_response)

    def _browser_video_list_by_id(self, list_id):
        self._browse_html_and_auth_url()
        path_response = self._post_browser_path_evaluator_with_fallback(
            self._browser_video_list_paths(str(list_id), include_metadata=True),
            self._browser_video_list_paths(str(list_id)),
            'https://www.netflix.com/browse',
            f'Browser list {list_id}')
        return VideoList(path_response, str(list_id))

    def _browser_mylist_loco_response(self, root_id, auth_url, row_range):
        return self._post_current_loco_paths([
            ['locos', root_id, 'componentSummary'],
            ['locos', root_id, row_range, 'componentSummary']
        ], auth_url)

    def _loco_row_key_for_list(self, root_response, root_id, list_id):
        root_data = root_response.get('locos', {}).get(root_id, {})
        for row_key, row_data in root_data.items():
            if row_key == 'componentSummary' or not isinstance(row_data, dict):
                continue
            row_ref = row_data.get('value')
            if isinstance(row_ref, list) and len(row_ref) > 1 and str(row_ref[1]) == str(list_id):
                return int(row_key) if str(row_key).isdigit() else row_key
        return None

    def _browser_mylist_list_info(self, root_id, auth_url):
        for row_range in (BROWSER_LOCO_HOME_VISIBLE_RANGE, BROWSER_LOCO_HOME_ROW_RANGE, LOCO_ROW_RANGE):
            try:
                root_response = self._browser_mylist_loco_response(root_id, auth_url, row_range)
            except req_exceptions.HTTPError as exc:
                if getattr(exc.response, 'status_code', None) not in (404, 412):
                    raise
                LOG.warn('My List queue lookup range {} returned {}; trying another range',
                         row_range, exc.response.status_code)
                continue
            list_id, _video_list = LoCo(root_response).find_by_context('queue')
            if list_id:
                return str(list_id), self._loco_row_key_for_list(root_response, root_id, list_id)
        raise InvalidVideoListTypeError('No current LoCo My List queue available')

    def _browser_mylist_loco_row_paths(self, root_id, row_key, use_direct_range, include_metadata=False):
        item_range = BROWSER_LOCO_DIRECT_RANGE if use_direct_range else LOCO_PAGE_RANGE
        row_path = ['locos', root_id, row_key]
        if use_direct_range:
            return [
                row_path + ['componentSummary'],
                row_path + [item_range, 'itemSummary'],
                *_browser_reference_paths(row_path + [item_range, 'reference'],
                                          include_metadata=include_metadata)
            ]
        return [
            row_path + ['componentSummary'],
            row_path + ['page', 0, item_range, 'itemSummary'],
            *_browser_reference_paths(row_path + ['page', 0, item_range, 'reference'],
                                      include_metadata=include_metadata)
        ]

    def _browser_mylist_loco_video_list(self, root_id, row_key, list_id, auth_url):
        for use_direct_range in (True, False):
            metadata_paths = self._browser_mylist_loco_row_paths(root_id, row_key, use_direct_range,
                                                                 include_metadata=True)
            light_paths = self._browser_mylist_loco_row_paths(root_id, row_key, use_direct_range)
            try:
                try:
                    path_response = self._post_current_loco_paths(metadata_paths, auth_url)
                except req_exceptions.HTTPError as exc:
                    status_code = getattr(exc.response, 'status_code', None)
                    if status_code not in (404, 412):
                        raise
                    LOG.warn('My List LoCo metadata fields request returned {}; retrying light fields',
                             status_code)
                    path_response = self._post_current_loco_paths(light_paths, auth_url)
                if str(list_id) in path_response.get('lists', {}):
                    return VideoList(path_response, str(list_id))
            except req_exceptions.HTTPError as exc:
                if getattr(exc.response, 'status_code', None) not in (404, 412):
                    raise
                LOG.warn('My List LoCo row content request returned {}; trying fallback path',
                         exc.response.status_code)
        raise InvalidVideoListTypeError('No current LoCo My List content available')

    def _browser_mylist_direct_video_list(self, list_id, auth_url):
        for paths, fallback_paths in (
                (self._browser_video_list_full_paths(str(list_id), include_metadata=True),
                 self._browser_video_list_full_paths(str(list_id))),
                (self._browser_video_list_paths(str(list_id), include_metadata=True),
                 self._browser_video_list_paths(str(list_id)))):
            try:
                try:
                    path_response = self._post_current_loco_paths(paths, auth_url)
                except req_exceptions.HTTPError as exc:
                    status_code = getattr(exc.response, 'status_code', None)
                    if status_code not in (404, 412):
                        raise
                    LOG.warn('My List direct metadata fields request returned {}; retrying light fields',
                             status_code)
                    path_response = self._post_current_loco_paths(fallback_paths, auth_url)
                return VideoList(path_response, str(list_id))
            except req_exceptions.HTTPError as exc:
                if getattr(exc.response, 'status_code', None) not in (404, 412):
                    raise
                LOG.warn('My List direct list content request returned {}; trying fallback path',
                         exc.response.status_code)
        raise InvalidVideoListTypeError('No current direct My List content available')

    def _browser_mylist_video_list(self):
        self._browse_html_and_auth_url()
        path_response = self._post_browser_path_evaluator([
            ['mylist', ['id', 'listId', 'name', 'requestId', 'trackIds']],
            ['mylist', BROWSER_MYLIST_RANGE, BROWSER_MYLIST_FIELDS]
        ], 'https://www.netflix.com/browse/my-list')
        mylist_data = path_response.get('mylist')
        if not isinstance(mylist_data, dict):
            raise InvalidVideoListTypeError('No browser My List data available')
        path_response['lists'] = {'mylist': mylist_data}
        _normalize_browser_video_fields(path_response)
        video_list = VideoList(path_response, 'mylist')
        for video in video_list.videos.values():
            video.setdefault('queue', _value({}))
            video['queue'].setdefault('value', {})['inQueue'] = True
        return video_list

    def _enrich_browser_video_list_metadata(self, path_response, list_id):
        videos = path_response.get('videos', {})
        for video_id in _browser_list_video_ids(path_response, list_id):
            video_key = next((key for key in videos if str(key) == video_id), None)
            if video_key is None:
                continue
            video = videos.get(video_key)
            if not isinstance(video, dict):
                continue
            fallback_art = common.get_path_safe(
                ['itemSummary', 'value', 'boxArt', 'url'], video)
            poster_art = common.get_path_safe(
                ['boxarts', ART_SIZE_POSTER, 'jpg', 'value', 'url'], video)
            synopsis = (video.get('synopsis', {}).get('value') or
                        video.get('regularSynopsis', {}).get('value'))
            if synopsis and poster_art and poster_art != fallback_art:
                continue
            try:
                metadata_video = self.nfsession._metadata(  # pylint: disable=protected-access
                    video_id=common.VideoId(videoid=video_id))
            except (MetadataNotAvailable, KeyError, TypeError, req_exceptions.RequestException):
                LOG.warn('LoLoMo metadata enrichment skipped for video {}', video_id)
                continue
            videos[video_key] = _merge_search_metadata_video(video, metadata_video)

    def _browser_lolomo_video_list_by_id(self, category_name, list_id):
        self._browse_html_and_auth_url()
        path_response = self._post_browser_path_evaluator(
            self._browser_loco_paths(['lolomoByCategory', category_name], include_full_rows=True),
            'https://www.netflix.com/latest')
        if str(list_id) not in path_response.get('lists', {}):
            raise InvalidVideoListTypeError(f'No LoLoMo category list with id {list_id}')
        return VideoList(path_response, str(list_id))

    def _browser_genre_video_list_by_id(self, genre_id, list_id):
        self._browse_html_and_auth_url()
        path_response = self._post_browser_path_evaluator_with_fallback(
            self._browser_loco_paths(['genres', int(genre_id), 'rw'], include_genre_paths=True,
                                     include_full_rows=True, include_metadata=True),
            self._browser_loco_paths(['genres', int(genre_id), 'rw'], include_genre_paths=True,
                                     include_full_rows=True),
            f'https://www.netflix.com/browse/genre/{genre_id}',
            f'Genre {genre_id}')
        if str(list_id) not in path_response.get('lists', {}):
            raise InvalidVideoListTypeError(f'No genre list with id {list_id}')
        return VideoList(path_response, str(list_id))

    def _browser_continue_watching_loco_response(self, root_id, auth_url, row_range):
        return self._post_current_loco_paths([
            ['locos', root_id, row_range, 'componentSummary'],
            ['locos', root_id, row_range, 'page', 0, LOCO_PAGE_RANGE, 'itemSummary'],
            *_browser_reference_paths(['locos', root_id, row_range, 'page', 0, LOCO_PAGE_RANGE, 'reference'])
        ], auth_url)

    def _continue_watching_list_id(self, root_response):
        candidates = []
        for candidate_id, list_data in root_response.get('lists', {}).items():
            summary = list_data.get('componentSummary', {}).get('value', {})
            if summary.get('context') != 'continueWatching':
                continue
            length = summary.get('length') or 0
            materialized_items = sum(1 for key, value in list_data.items()
                                     if str(key).isdigit() and isinstance(value, dict))
            candidates.append((length, materialized_items, candidate_id))
        return max(candidates)[2] if candidates else None

    def _browser_continue_watching_direct_response(self, list_id):
        return self._post_browser_path_evaluator([
            ['lists', list_id, ['componentSummary', 'debugRequest']],
            ['lists', list_id, BROWSER_LOCO_DIRECT_RANGE, 'itemSummary'],
            *_browser_reference_paths(['lists', list_id, BROWSER_LOCO_DIRECT_RANGE, 'reference']),
            ['lists', list_id, BROWSER_LOCO_DIRECT_RANGE, 'reference', 'current',
             BROWSER_LOCO_CONTINUE_FIELDS]
        ], 'https://www.netflix.com/browse')

    def _browser_continue_watching_list(self):
        try:
            return self._browser_continue_watching_graphql_list()
        except (InvalidVideoListTypeError, WebsiteParsingError, KeyError, TypeError,
                ValueError, req_exceptions.RequestException) as exc:
            LOG.warn('GraphQL Continue Watching lookup failed ({}); using genre fallback',
                     type(exc).__name__)
            return self._browser_continue_watching_genre_fallback()

    def _browser_continue_watching_graphql_list(self):
        graphql_data, section, connection = self._browser_graphql_carousel_section(
            self._continue_watching_graphql_section)
        videos = OrderedDict()
        self._append_continue_watching_graphql_edges(
            videos, graphql_data, _iter_graphql_edges(connection))
        page_info = connection.get('pageInfo') or {}
        while page_info.get('hasNextPage') and page_info.get('endCursor'):
            data = self._post_graphql(
                'CarouselPage',
                _carousel_graphql_variables(section.get('_id') or section['id'], page_info['endCursor']),
                GRAPHQL_OP_CAROUSEL_PAGE)
            next_section = data.get('node') or {}
            next_connection = next_section.get('entities') or {}
            previous_count = len(videos)
            self._append_continue_watching_graphql_edges(
                videos, {}, _iter_graphql_edges(next_connection))
            page_info = next_connection.get('pageInfo') or {}
            if len(videos) == previous_count:
                break
        if not videos:
            raise InvalidVideoListTypeError('No GraphQL Continue Watching videos available')
        return CustomVideoList({'videos': videos})

    def _browser_top_picks_list(self):
        """Return the personalized Top Picks carousel from the active home page."""
        graphql_data, _section, connection = self._browser_graphql_carousel_section(
            self._top_picks_graphql_section)
        videos = OrderedDict()
        self._append_standard_graphql_edges(
            videos, graphql_data, _iter_graphql_edges(connection))
        if not videos:
            raise InvalidVideoListTypeError('No GraphQL Top Picks videos available')
        LOG.debug('GraphQL Top Picks returned {} personalized videos', len(videos))
        return CustomVideoList({'videos': videos})

    def _browser_graphql_carousel_section(self, section_resolver):
        browse_html = self.nfsession.get_safe('browse')
        graphql_data = self._browser_graphql_data(browse_html)
        try:
            section, connection = section_resolver(graphql_data)
        except InvalidVideoListTypeError as section_error:
            try:
                browse_html = self._active_profile_browse_html(browse_html)
            except InvalidVideoListTypeError:
                raise section_error
            graphql_data = self._browser_graphql_data(browse_html)
            section, connection = section_resolver(graphql_data)
        return graphql_data, section, connection

    def _browser_graphql_data(self, browse_html):
        api_data = self.nfsession.website_extract_session_data(browse_html)
        self.nfsession.auth_url = api_data['auth_url']
        react_context = website.extract_json(browse_html, 'reactContext')
        return _title_page_graphql_data(browse_html, react_context)

    def _active_profile_browse_html(self, profile_gate_html):
        parser = _ActiveProfileLinkParser(G.LOCAL_DB.get_active_profile_guid())
        parser.feed(profile_gate_html.decode('utf-8', 'replace')
                    if isinstance(profile_gate_html, bytes) else str(profile_gate_html))
        if not parser.href:
            raise InvalidVideoListTypeError('No active profile switch link available')
        response = self.nfsession.session.get(
            urljoin('https://www.netflix.com/browse', parser.href),
            headers={
                'Accept': 'text/html,application/xhtml+xml,application/xml',
                'Referer': 'https://www.netflix.com/browse',
                'User-Agent': common.get_user_agent(enable_android_mediaflag_fix=True)
            },
            timeout=8)
        response.raise_for_status()
        return response.content

    @staticmethod
    def _continue_watching_graphql_section(graphql_data):
        for section in graphql_data.values():
            if not isinstance(section, dict) or section.get('__typename') != 'PinotCarouselSection':
                continue
            connection = _graphql_ref_node(graphql_data, section.get('entities'))
            if not isinstance(connection, dict):
                continue
            for edge in _iter_graphql_edges(connection):
                edge_data = _graphql_ref_node(graphql_data, edge)
                node = _graphql_ref_node(graphql_data, (edge_data or {}).get('node'))
                if isinstance(node, dict) and node.get('__typename') == 'PinotContinueWatchingEntityTreatment':
                    return section, connection
        raise InvalidVideoListTypeError('No GraphQL Continue Watching section available')

    @staticmethod
    def _top_picks_graphql_section(graphql_data):
        labels = {
            TOP_PICKS_SECTION_LABEL,
            str(common.get_local_string(30169) or '').casefold()
        }
        for section in graphql_data.values():
            if not isinstance(section, dict) or section.get('__typename') != 'PinotCarouselSection':
                continue
            label = str(section.get('displayString') or '').casefold()
            if not any(candidate and candidate in label for candidate in labels):
                continue
            connection = _graphql_ref_node(graphql_data, section.get('entities'))
            if isinstance(connection, dict):
                return section, connection
        raise InvalidVideoListTypeError('No personalized GraphQL Top Picks section available')

    @staticmethod
    def _continue_watching_graphql_node(graphql_data, edge):
        edge_data = _graphql_ref_node(graphql_data, edge) if graphql_data else edge
        node = ((edge_data or {}).get('node') or {})
        node = _graphql_ref_node(graphql_data, node) if graphql_data else node
        if not isinstance(node, dict):
            return None
        entity = node.get('unifiedEntity') or {}
        entity = _graphql_ref_node(graphql_data, entity) if graphql_data else entity
        artwork_context = node.get('contextualArtwork') or {}
        artwork_context = (_graphql_ref_node(graphql_data, artwork_context)
                           if graphql_data else artwork_context)
        artwork = {}
        if isinstance(artwork_context, dict):
            artwork_value = next(
                (value for key, value in artwork_context.items() if key == 'artwork' or key.startswith('artwork(')),
                {})
            artwork = (_graphql_ref_node(graphql_data, artwork_value)
                       if graphql_data else artwork_value)
        return {
            'displayString': node.get('displayString'),
            'unifiedEntity': entity or {},
            'contextualArtwork': {'artwork': artwork or {}}
        }

    def _append_continue_watching_graphql_edges(self, videos, graphql_data, edges):
        for edge in edges:
            node = self._continue_watching_graphql_node(graphql_data, edge)
            item_data = _search_graphql_node_to_item(node or {})
            if not item_data:
                continue
            video_id, item = item_data
            entity = node.get('unifiedEntity') or {}
            progress_entity = entity.get('currentEpisode') or entity
            if graphql_data:
                progress_entity = _graphql_ref_node(graphql_data, progress_entity) or progress_entity
            bookmark = progress_entity.get('bookmark') or {}
            if graphql_data:
                bookmark = _graphql_ref_node(graphql_data, bookmark) or bookmark
            item['bookmarkPosition'] = _value(bookmark.get('position', 0))
            item['runtime'] = _value(progress_entity.get('runtimeSec') or entity.get('runtimeSec') or 0)
            videos[video_id] = item

    def _append_standard_graphql_edges(self, videos, graphql_data, edges):
        for edge in edges:
            node = self._continue_watching_graphql_node(graphql_data, edge)
            item_data = _search_graphql_node_to_item(node or {})
            if not item_data:
                continue
            video_id, item = item_data
            videos.setdefault(video_id, item)

    def _browser_continue_watching_loco_list(self):
        try:
            root_id, auth_url = self._get_current_loco_root_id()
        except InvalidVideoListTypeError:
            return self._browser_continue_watching_genre_fallback()
        root_response = self._browser_continue_watching_loco_response(
            root_id, auth_url, BROWSER_LOCO_HOME_ROW_RANGE)
        list_id = self._continue_watching_list_id(root_response)
        if not list_id:
            root_response = self._browser_continue_watching_loco_response(
                root_id, auth_url, BROWSER_LOCO_HOME_VISIBLE_RANGE)
            list_id = self._continue_watching_list_id(root_response)
        if not list_id:
            raise InvalidVideoListTypeError('No current home Continue Watching list available')
        try:
            direct_response = self._browser_continue_watching_direct_response(list_id)
            root_response.setdefault('lists', {}).setdefault(list_id, {}).update(
                direct_response.get('lists', {}).get(list_id, {}))
            root_response.setdefault('videos', {}).update(direct_response.get('videos', {}))
            _normalize_browser_video_fields(root_response)
        except req_exceptions.HTTPError as exc:
            if getattr(exc.response, 'status_code', None) not in (404, 412):
                raise
            LOG.warn('Continue Watching direct list range returned {}; using home row data',
                     exc.response.status_code)
        length = root_response['lists'][list_id].get('componentSummary', {}).get('value', {}).get('length', 0)
        if length > BROWSER_LOCO_CONTINUE_LAZY_RANGE['from']:
            try:
                lazy_response = self._post_browser_path_evaluator([
                    ['lists', list_id, BROWSER_LOCO_CONTINUE_LAZY_RANGE, 'itemSummary'],
                    *_browser_reference_paths(['lists', list_id, BROWSER_LOCO_CONTINUE_LAZY_RANGE, 'reference']),
                    ['lists', list_id, BROWSER_LOCO_CONTINUE_LAZY_RANGE, 'reference', 'current',
                     BROWSER_LOCO_CONTINUE_FIELDS]
                ], 'https://www.netflix.com/browse')
                root_response.setdefault('lists', {}).setdefault(list_id, {}).update(
                    lazy_response.get('lists', {}).get(list_id, {}))
                root_response.setdefault('videos', {}).update(lazy_response.get('videos', {}))
                _normalize_browser_video_fields(root_response)
            except req_exceptions.HTTPError as exc:
                if getattr(exc.response, 'status_code', None) not in (404, 412):
                    raise
                LOG.warn('Continue Watching lazy range returned {}; using available row data',
                         exc.response.status_code)
        return VideoList(root_response, str(list_id))

    def _browser_continue_watching_genre_fallback(self):
        LOG.warn('Home LoCo discovery failed for Continue Watching; using genre fallback')
        try:
            loco_list = self.req_loco_list_genre('1592210')
            for list_id, video_list in loco_list.lists.items():
                if video_list.get('context') != 'continueWatching':
                    continue
                try:
                    return self._browser_genre_video_list_by_id('1592210', list_id)
                except Exception:  # pylint: disable=broad-except
                    LOG.warn('Using materialized Continue Watching genre row after browser list lookup failed')
                    return video_list
        except Exception:  # pylint: disable=broad-except
            LOG.warn('Continue Watching genre fallback failed after home LoCo discovery failure')
        return CustomVideoList({'videos': {}})

    def _first_loco_video_list(self, loco):
        for _list_id, video_list in loco.lists.items():
            if video_list.videos:
                return video_list
        return next(iter(loco.lists.values()))

    def _first_full_browser_genre_video_list(self, genre_id):
        loco = self._req_browser_genre_loco(genre_id)
        first_list_id = None
        first_video_list = None
        for list_id, video_list in loco.lists.items():
            if first_list_id is None:
                first_list_id = list_id
                first_video_list = video_list
            if video_list.videos:
                first_list_id = list_id
                first_video_list = video_list
                break
        if first_list_id is None:
            raise InvalidVideoListTypeError(f'No browser genre rows available for {genre_id}')
        try:
            return self._browser_genre_video_list_by_id(genre_id, first_list_id)
        except Exception as exc:  # pylint: disable=broad-except
            LOG.warn('Using materialized genre preview row after full row lookup failed: {}', exc)
            return first_video_list

    def _req_current_loco_root_data(self):
        root_id, auth_url = self._get_current_loco_root_id()
        return self._post_current_loco_paths(self._current_loco_paths(root_id), auth_url)

    def _current_loco_list_by_context(self, context):
        loco = LoCo(self._req_current_loco_root_data())
        list_id, video_list = loco.find_by_context(context)
        if not list_id:
            category_contexts = LOCO_CATEGORY_CONTEXTS.get('comingSoon', ())
            if context in category_contexts:
                for _list_id, summary, category_video_list in self.req_lolomo_category('comingSoon').lists():
                    if summary.get('context') == context:
                        return category_video_list
            raise InvalidVideoListTypeError(f'No current LoCo list with context {context} available')
        return video_list

    def _current_loco_list_by_id(self, list_id):
        loco = LoCo(self._req_current_loco_root_data())
        if str(list_id) not in loco.data.get('lists', {}):
            raise InvalidVideoListTypeError(f'No current LoCo list with id {list_id} available')
        return VideoList(loco.data, str(list_id))

    def _current_lolomo_category(self, category_name):
        contexts = LOCO_CATEGORY_CONTEXTS.get(category_name)
        if not contexts:
            raise InvalidVideoListTypeError(f'No current LoCo fallback for category {category_name}')
        loco = LoCo(self._req_current_loco_root_data())
        lists = OrderedDict(
            (list_id, list_data)
            for list_id, list_data in loco.data.get('lists', {}).items()
            if list_data.get('componentSummary', {}).get('value', {}).get('context') in contexts)
        root_id = loco.id
        root = OrderedDict()
        root['componentSummary'] = _value({'length': len(lists)})
        for index, list_id in enumerate(lists):
            root[index] = {
                'reference': _value(['lists', list_id]),
                'itemSummary': _value({'id': list_id})
            }
        return LoLoMoCategory({
            'locos': {root_id: root},
            'lists': lists,
            'videos': loco.data.get('videos', {})
        })


    @cache_utils.cache_output(cache_utils.CACHE_COMMON, identify_append_from_kwarg_name='perpetual_range_start',
                              ignore_self_class=True)
    def req_video_list(self, list_id, perpetual_range_start=None, menu_data=None):
        """Retrieve a video list"""
        # Some of this type of request have results fixed at ~40 from netflix
        # The 'length' tag never return to the actual total count of the elements
        LOG.debug('Requesting video list {}', list_id)
        browser_genre_id = str((menu_data or {}).get('browser_genre_id') or '')
        if browser_genre_id:
            if str(list_id) == browser_genre_id:
                return self._first_full_browser_genre_video_list(browser_genre_id)
            return self._browser_genre_video_list_by_id(browser_genre_id, list_id)
        paths = (build_paths(['lists', list_id, RANGE_PLACEHOLDER, 'reference'], VIDEO_LIST_PARTIAL_PATHS) +
                 [['lists', list_id, 'componentSummary']])
        call_args = {
            'paths': paths,
            'length_params': ['stdlist', ['lists', list_id]],
            'perpetual_range_start': perpetual_range_start
        }
        try:
            path_response = self.nfsession.perpetual_path_request(**call_args)
        except req_exceptions.HTTPError as exc:
            if getattr(exc.response, 'status_code', None) != 404:
                raise
            initial_menu_id = (menu_data or {}).get('initial_menu_id')
            if initial_menu_id in ('newAndPopular', 'recommendations'):
                LOG.warn('Falling back to browser-shaped LoLoMo category list {} after pathEvaluator 404', list_id)
                return self._browser_lolomo_video_list_by_id('comingSoon', list_id)
            LOG.warn('Falling back to browser-shaped list {} after pathEvaluator 404', list_id)
            try:
                return self._browser_video_list_by_id(list_id)
            except req_exceptions.HTTPError:
                return self._current_loco_list_by_id(list_id)
        return VideoList(path_response)

    @cache_utils.cache_output(cache_utils.CACHE_COMMON, identify_from_kwarg_name='context_id',
                              identify_append_from_kwarg_name='perpetual_range_start', ignore_self_class=True)
    def req_video_list_sorted(self, context_name, context_id=None, perpetual_range_start=None, menu_data=None):
        """Retrieve a video list sorted"""
        # This type of request allows to obtain more than ~40 results
        LOG.debug('Requesting video list sorted for context name: "{}", context id: "{}"',
                  context_name, context_id)
        if context_name == 'mylist':
            try:
                return self._browser_mylist_video_list()
            except InvalidVideoListTypeError:
                LOG.warn('Returning empty My List after current queue lookup failed')
                return CustomVideoList({'videos': {}})
            except req_exceptions.HTTPError as exc:
                if getattr(exc.response, 'status_code', None) not in (404, 412):
                    raise
                LOG.warn('Returning empty My List after browser-shaped request returned {}',
                         exc.response.status_code)
                return CustomVideoList({'videos': {}})

        base_path = [context_name]
        response_type = 'stdlist'
        if context_id:
            base_path.append(context_id)
            response_type = 'stdlist_wid'

        # enum order: AZ|ZA|Suggested|Year
        # sort order the "mylist" is supported only in US country, the only way to query is use 'az'
        sort_order_types = ['az', 'za', 'su', 'yr'] if not context_name == 'mylist' else ['az', 'az']
        req_sort_order_type = sort_order_types[
            int(G.ADDON.getSettingInt('menu_sortorder_' + menu_data.get('initial_menu_id', menu_data['path'][1])))
        ]
        base_path.append(req_sort_order_type)
        _base_path = list(base_path)
        _base_path.append(RANGE_PLACEHOLDER)
        if not menu_data.get('query_without_reference', False):
            _base_path.append('reference')
        paths = (build_paths(_base_path, VIDEO_LIST_PARTIAL_PATHS) +
                 [base_path[:-1] + [['id', 'name', 'requestId', 'trackIds']]])

        try:
            path_response = self.nfsession.perpetual_path_request(paths, [response_type, base_path], perpetual_range_start)
        except req_exceptions.HTTPError as exc:
            status_code = getattr(exc.response, 'status_code', None)
            if status_code not in (404, 412):
                raise
            context = SORTED_LIST_CONTEXT_FALLBACKS.get((context_name, str(context_id)))
            if context_name != 'genres' and not context:
                raise
            LOG.warn('Falling back to browser-shaped genre {} after pathEvaluator {}', context_id, status_code)
            return self._first_full_browser_genre_video_list(context_id)
        return VideoListSorted(path_response, context_name, context_id, req_sort_order_type)


    @cache_utils.cache_output(cache_utils.CACHE_COMMON, identify_from_kwarg_name='context_id',
                              identify_append_from_kwarg_name='perpetual_range_start', ignore_self_class=True)
    def req_videos_list_sorted(self, context_name, context_id=None, perpetual_range_start=None, menu_data=None):
        """Retrieve a video's list sorted"""
        # This type of request allows to obtain more than ~40 results
        LOG.debug('Requesting video\'s list sorted for context name: "{}", context id: "{}"',
                  context_name, context_id)
        base_path = [context_name]
        response_type = 'videoslist'
        if context_id:
            base_path.append(context_id)

        # enum order: AZ|ZA|Suggested|Year
        # sort order the "mylist" is supported only in US country, the only way to query is use 'az'
        sort_order_types = ['az', 'za', 'su', 'yr'] if context_name != 'mylist' else ['az', 'az']
        req_sort_order_type = sort_order_types[
            int(G.ADDON.getSettingInt('menu_sortorder_' + menu_data.get('initial_menu_id', menu_data['path'][1])))
        ]
        base_path.append(req_sort_order_type)
        _base_path = list(base_path)
        _base_path.append(RANGE_PLACEHOLDER)
        if not menu_data.get('query_without_reference', False):
            _base_path.append('reference')
        paths = (build_paths(_base_path, VIDEO_LIST_PARTIAL_PATHS) +
                 [base_path[:-1] + [['id', 'name', 'requestId', 'trackIds']]])

        path_response = self.nfsession.perpetual_path_request(paths, [response_type, ['videos']], perpetual_range_start)
        return VideosList(path_response, [context_name, context_id])

    @cache_utils.cache_output(cache_utils.CACHE_SUPPLEMENTAL, identify_append_from_kwarg_name='supplemental_type',
                              ignore_self_class=True)
    def req_video_list_supplemental(self, videoid, supplemental_type):
        """Retrieve a video list of supplemental type videos"""
        if videoid.mediatype not in (common.VideoId.SHOW, common.VideoId.MOVIE):
            raise InvalidVideoId(f'Cannot request video list supplemental for {videoid}')
        LOG.debug('Requesting video list supplemental of type "{}" for {}', supplemental_type, videoid)
        if supplemental_type == SUPPLEMENTAL_TYPE_TRAILERS:
            try:
                trailer_list = self._req_video_list_supplemental_graphql(videoid)
                if trailer_list.videos:
                    return trailer_list
                LOG.warn('Website GraphQL returned no trailers for {}', videoid)
                return trailer_list
            except (KeyError, TypeError, ValueError, req_exceptions.RequestException) as exc:
                LOG.warn('Website trailer collection lookup failed for {} ({}), trying title page fallback',
                         videoid, type(exc).__name__)
                return self._req_video_list_supplemental_title_page(videoid)

        path = build_paths(
            ['videos', videoid.value, supplemental_type, {"from": 0, "to": 35}], TRAILER_PARTIAL_PATHS
        )
        parent_metadata = {'loaded': False, 'value': None}

        def _get_parent_metadata():
            if not parent_metadata['loaded']:
                parent_metadata['loaded'] = True
                parent_metadata['value'] = self._metadata_for_video(videoid.value, 'Parent supplemental')
            return parent_metadata['value']

        def _inherit_parent_metadata(video_list):
            metadata_video = _get_parent_metadata()
            if metadata_video:
                for supplemental_id, supplemental_video in video_list.videos.items():
                    normalize_metadata_references(video_list.data, supplemental_id, metadata_video, supplemental_video)
            return video_list

        def _empty_fallback():
            return SimpleNamespace(
                perpetual_range_selector=None,
                videos=OrderedDict(),
                artitem=None,
                contained_titles=[],
                component_summary={})

        def _title_page_fallback():
            trailer_list = self._req_video_list_supplemental_title_page(videoid)
            return _inherit_parent_metadata(trailer_list) if trailer_list.videos else _empty_fallback()
        try:
            path_response = self.nfsession.path_request(path)
            trailer_list = VideoListSupplemental(path_response, 'videos', videoid.value, supplemental_type)
            if trailer_list.videos:
                return _inherit_parent_metadata(trailer_list)
            LOG.warn('Trailer supplemental response was empty for {}, trying title page fallback', videoid)
            return _title_page_fallback()
        except req_exceptions.HTTPError as exc:
            if getattr(exc.response, 'status_code', None) != 404:
                raise
            LOG.warn('Trailer supplemental path returned 404 for {}, trying title page fallback', videoid)
            return _title_page_fallback()

    def _req_video_list_supplemental_graphql(self, videoid):
        """Load the website's ordered Trailers & More collection."""
        video_id = int(videoid.value)
        detail_data = self._post_graphql(
            'DetailModal',
            {
                'artworkContext': {},
                'checkLinearChannel': True,
                'fetchPromoVideoOverride': False,
                'hasPromoVideoOverride': False,
                'isLiveEpisodic': False,
                'opaqueImageFormat': 'WEBP',
                'promoVideoId': 0,
                'textEvidenceUiContext': 'ODP',
                'transparentImageFormat': 'WEBP',
                'unifiedEntityId': f'Video:{video_id}',
                'videoId': video_id,
                'videoMerchContext': 'BROWSE',
                'videoMerchEnabled': False
            },
            GRAPHQL_OP_DETAIL_MODAL)
        entity = (detail_data.get('unifiedEntities') or [None])[0] or {}
        edges = common.get_path_safe(['supplementalVideosList', 'edges'], entity, False, [])
        trailer_ids = []
        for edge in edges:
            node = edge.get('node') or edge
            trailer_id = node.get('videoId')
            if trailer_id and trailer_id not in trailer_ids:
                trailer_ids.append(trailer_id)
        if not trailer_ids:
            return self._empty_supplemental_list()

        trailer_data = self._post_graphql(
            'DetailModalTrailers',
            {
                'artworkContext': {},
                'opaqueImageFormat': 'WEBP',
                'videoIds': trailer_ids
            },
            GRAPHQL_OP_DETAIL_MODAL_TRAILERS)
        nodes_by_id = {
            str(node.get('videoId')): node
            for node in trailer_data.get('videos') or []
            if isinstance(node, dict) and node.get('videoId')
        }
        videos = OrderedDict()
        for trailer_id in trailer_ids:
            item = _supplemental_node_to_item(nodes_by_id.get(str(trailer_id), {}))
            if item:
                videos[item[0]] = item[1]
        trailer_list = CustomVideoList({'videos': videos})
        trailer_list.is_supplemental_type = True
        trailer_list.component_summary = {}
        LOG.debug('Website GraphQL returned {} trailers for {}', len(videos), videoid)
        return trailer_list

    def _req_video_list_supplemental_title_page(self, videoid):
        try:
            response = self.nfsession.session.get(
                NETFLIX_TITLE_URL.format(videoid.value),
                headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml',
                    'User-Agent': common.get_user_agent(enable_android_mediaflag_fix=True)
                },
                timeout=8)
            response.raise_for_status()
            react_context = website.extract_json(response.content, 'reactContext')
        except (req_exceptions.RequestException, WebsiteParsingError) as exc:
            LOG.warn('Title page trailer fallback failed for {} ({})', videoid, type(exc).__name__)
            return self._empty_supplemental_list()
        graphql_data = _title_page_graphql_data(response.content, react_context)
        videos = _supplemental_videos_from_graphql_cache(graphql_data, videoid.value)
        if not videos:
            LOG.warn('No title page supplemental videos found for {}', videoid)
            return self._empty_supplemental_list()
        LOG.debug('Title page trailer fallback found {} supplemental videos for {}', len(videos), videoid)
        trailer_list = CustomVideoList({'videos': videos})
        trailer_list.is_supplemental_type = True
        trailer_list.component_summary = {}
        return trailer_list

    @staticmethod
    def _empty_supplemental_list():
        trailer_list = CustomVideoList({'videos': OrderedDict()})
        trailer_list.is_supplemental_type = True
        trailer_list.component_summary = {}
        return trailer_list

    @cache_utils.cache_output(cache_utils.CACHE_COMMON, identify_from_kwarg_name='chunked_video_list',
                              ttl=900, ignore_self_class=True)
    def req_video_list_chunked(self, chunked_video_list, perpetual_range_selector=None):
        """Retrieve a video list which contains the video ids specified"""
        if not any(isinstance(item, list) for item in chunked_video_list):
            raise InvalidVideoListTypeError('The chunked_video_list not contains a list of a list of videoids')
        merged_response = {}
        for videoids_list in chunked_video_list:
            path = build_paths(['videos', videoids_list], VIDEO_LIST_PARTIAL_PATHS)
            path_response = self.nfsession.path_request(path)
            common.merge_dicts(path_response, merged_response)

        if perpetual_range_selector:
            merged_response.update(perpetual_range_selector)
        return CustomVideoList(merged_response)

    def req_video_list_search(self, search_term, perpetual_range_start=None):
        """Retrieve a video list by search term"""
        LOG.debug('Requesting video list by search term "{}"', search_term)
        return self._req_video_list_search_graphql(search_term)

    def _req_video_list_search_graphql(self, search_term):
        data = self._post_graphql(
            'SearchPageQueryResults',
            _search_graphql_variables(search_term),
            GRAPHQL_OP_SEARCH)
        videos = OrderedDict()
        path_response = {'videos': videos}
        page = data.get('page') or {}
        sections = (page.get('sections') or {}).get('edges') or []
        for section in sections:
            section_node = section.get('node') or {}
            if section_node.get('__typename') != 'PinotGallerySection':
                continue
            entities = (section_node.get('entities') or {}).get('edges') or []
            for entity_edge in entities:
                item = _search_graphql_node_to_item(entity_edge.get('node') or {})
                if item:
                    video_id, video_data = item
                    videos.setdefault(video_id, video_data)
        self._enrich_search_video_list(path_response)
        LOG.debug('GraphQL search returned {} video results for "{}"', len(videos), search_term)
        return CustomVideoList(path_response)

    def _enrich_search_video_list(self, path_response):
        videos = path_response.get('videos') or {}
        video_ids = list(videos)[:SEARCH_TITLE_PAGE_METADATA_LIMIT]
        if not video_ids:
            return
        metadata_by_video = {video_id: {} for video_id in video_ids}
        title_metadata_by_video = {}
        max_workers = min(SEARCH_TITLE_PAGE_METADATA_WORKERS, len(video_ids))
        try:
            metadata_request = self._prepare_metadata_request()
        except Exception as exc:  # pylint: disable=broad-except
            LOG.debug('Search metadata request setup failed ({})', type(exc).__name__)
            metadata_request = None
        with ThreadPoolExecutor(max_workers=max_workers) as metadata_executor:
            with ThreadPoolExecutor(max_workers=max_workers) as title_executor:
                metadata_futures = ({
                    metadata_executor.submit(
                        self._metadata_for_video_from_request, video_id, metadata_request): video_id
                    for video_id in video_ids
                } if metadata_request else {})
                title_futures = {
                    title_executor.submit(_search_title_page_metadata, video_id): video_id
                    for video_id in video_ids
                }
                for future in as_completed(metadata_futures):
                    video_id = metadata_futures[future]
                    try:
                        metadata_by_video[video_id] = future.result()
                    except Exception as exc:  # pylint: disable=broad-except
                        LOG.debug('Search metadata worker failed ({})', type(exc).__name__)
                for future in as_completed(title_futures):
                    video_id = title_futures[future]
                    try:
                        title_metadata_by_video[video_id] = future.result()
                    except Exception as exc:  # pylint: disable=broad-except
                        LOG.debug('Search title metadata worker failed ({})', type(exc).__name__)
        for video_id in video_ids:
            metadata = _merge_title_page_metadata(
                metadata_by_video[video_id], title_metadata_by_video.get(video_id))
            video = _merge_search_metadata_video(videos[video_id], metadata)
            videos[video_id] = video
            normalize_metadata_references(path_response, video_id, metadata, video)

    def _enrich_search_title_page_metadata(self, metadata_by_video):
        video_ids = [
            video_id
            for video_id, metadata_video in metadata_by_video.items()
            if not _metadata_has_reference_names(metadata_video)
        ][:SEARCH_TITLE_PAGE_METADATA_LIMIT]
        if not video_ids:
            return
        max_workers = min(SEARCH_TITLE_PAGE_METADATA_WORKERS, len(video_ids))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_by_video_id = {
                executor.submit(_search_title_page_metadata, video_id): video_id
                for video_id in video_ids
            }
            for future in as_completed(future_by_video_id):
                video_id = future_by_video_id[future]
                try:
                    title_page_metadata = future.result()
                except Exception as exc:  # pylint: disable=broad-except
                    LOG.debug('Search title page metadata failed for {} ({})', video_id, type(exc).__name__)
                    continue
                metadata_by_video[video_id] = _merge_title_page_metadata(
                    metadata_by_video.get(video_id), title_page_metadata)

    def _prepare_metadata_request(self):
        # Resolve DB-backed auth/profile state before worker threads start. The add-on's
        # shared SQLite connection and requests session are not safe for concurrent use.
        endpoint_conf = ENDPOINTS['metadata']
        _, headers, params = self.nfsession._prepare_request_properties(  # pylint: disable=protected-access
            endpoint_conf, {'params': {}})
        request_headers = dict(self.nfsession.session.headers)
        request_headers.update(headers)
        # Stored Netflix cookies use PickleableCookieJar (a plain CookieJar),
        # which has no .copy() method. Clone it into RequestsCookieJar so a
        # missing method cannot disable all list/search metadata enrichment.
        request_cookies = requests.cookies.merge_cookies(
            requests.cookies.RequestsCookieJar(), self.nfsession.session.cookies)
        api_url = G.LOCAL_DB.get_value('api_endpoint_url', table=TABLE_SESSION)
        return SimpleNamespace(
            url=f"{api_url.rstrip('/')}{endpoint_conf['address']}",
            headers=request_headers,
            params=params,
            cookies=request_cookies)

    @staticmethod
    def _metadata_for_video_from_request(video_id, metadata_request):
        try:
            params = dict(metadata_request.params)
            params.update({'movieid': video_id, '_': int(time.time() * 1000)})
            response = requests.get(
                metadata_request.url,
                headers=metadata_request.headers,
                params=params,
                cookies=metadata_request.cookies,
                timeout=(2, 4))
            response.raise_for_status()
            metadata_data = response.json() if response.content else {}
            return metadata_data.get('video') or {}
        except (MetadataNotAvailable, KeyError, TypeError, ValueError, req_exceptions.RequestException):
            LOG.debug('Search metadata enrichment skipped for video {}', video_id)
            return {}

    def _metadata_for_video(self, video_id, context):
        try:
            metadata_data = self.nfsession.get_safe(
                endpoint='metadata',
                params={'movieid': video_id, '_': int(time.time() * 1000)})
            return metadata_with_title_page_fallback(video_id, metadata_data.get('video') or {})
        except (MetadataNotAvailable, KeyError, TypeError, req_exceptions.RequestException):
            LOG.warn('{} metadata enrichment skipped for video {}', context, video_id)
            return metadata_with_title_page_fallback(video_id)

    def req_subgenres(self, genre_id):
        """Retrieve sub-genres for the given genre"""
        LOG.debug('Requesting sub-genres of the genre {}', genre_id)
        path = [['genres', genre_id, 'subgenres', {'from': 0, 'to': 47}, ['id', 'name']]]
        path_response = self.nfsession.path_request(path)
        return SubgenreList(path_response)

    def req_datatype_video_list_full(self, context_name, switch_profiles=False):
        """
        Retrieve the FULL video list for a context name (no limits to the number of path requests)
        contains only minimal video info
        """
        LOG.debug('Requesting the full video list for {}', context_name)
        if context_name == 'mylist' and not switch_profiles:
            return self._browser_mylist_video_list()

        paths = (build_paths([context_name, 'az', RANGE_PLACEHOLDER], VIDEO_LIST_BASIC_PARTIAL_PATHS) +
                 [[context_name, ['id', 'name', 'requestId', 'trackIds']]])
        call_args = {
            'paths': paths,
            'length_params': ['stdlist', [context_name, 'az']],
            'perpetual_range_start': None,
            'request_size': PATH_REQUEST_SIZE_MAX,
            'no_limit_req': True
        }
        if switch_profiles:
            # Used only with library auto-update with the sync with Netflix "My List" enabled.
            # It may happen that the user browses the frontend with a different profile used by library sync,
            # and it could cause a wrong query request to nf server.
            # So we try to switch the profile, get My List items and restore previous
            # active profile in a "single call" to try perform the operations in a faster way.
            path_response = self.nfsession.perpetual_path_request_switch_profiles(**call_args)
        else:
            path_response = self.nfsession.perpetual_path_request(**call_args)
        return None if not path_response else VideoListSorted(path_response, context_name, None, 'az')

    def req_datatype_video_list_byid(self, video_ids, custom_partial_paths=None):
        """Retrieve a video list which contains the specified by video ids and return a CustomVideoList object"""
        LOG.debug('Requesting a video list for {} videos', video_ids)
        paths = build_paths(['videos', video_ids],
                            custom_partial_paths if custom_partial_paths else VIDEO_LIST_PARTIAL_PATHS)
        try:
            path_response = self.nfsession.path_request(paths)
            return CustomVideoList(path_response)
        except req_exceptions.HTTPError as exc:
            status_code = getattr(exc.response, 'status_code', None)
            if status_code not in (404, 412):
                raise
            LOG.warn('Falling back to metadata video list for {} videos after pathEvaluator {}',
                     len(video_ids), status_code)
        videos = OrderedDict()
        for video_id in video_ids:
            metadata_video = self._metadata_for_video(str(video_id), 'Video id list')
            if metadata_video:
                videos[str(video_id)] = _metadata_video_to_item(str(video_id), metadata_video)
        return CustomVideoList({'videos': videos})

    @cache_utils.cache_output(cache_utils.CACHE_COMMON, fixed_identifier='lolomo_category',
                              identify_append_from_kwarg_name='category_name', ignore_self_class=True)
    def req_lolomo_category(self, category_name):
        """Retrieve LoLoMo by category lists"""
        LOG.debug('Requesting LoLoMo "{}" category lists', category_name)
        try:
            return self._req_browser_lolomo_category(category_name)
        except req_exceptions.HTTPError as exc:
            if exc.response is None or exc.response.status_code not in (404, 412):
                raise
            LOG.warn('Falling back to current LoCo rows for LoLoMo category after pathEvaluator {}', exc.response.status_code)
            return self._current_lolomo_category(category_name)
