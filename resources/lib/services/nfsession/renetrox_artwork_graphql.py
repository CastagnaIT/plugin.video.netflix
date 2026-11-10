# -*- coding: utf-8 -*-
"""Experimental GraphQL artwork fetch using CastagnaIT's existing authenticated session.

Artwork source/mapping researched by the original author of issue #1807:
https://github.com/CastagnaIT/plugin.video.netflix/issues/1807

This is a proof of concept, not a replacement for the original research branch.
A rejected query or absent artwork must never prevent the catalog from loading.
"""
from urllib.parse import urlsplit

from resources.lib.utils.logging import LOG

_QUERY_ID = 'e5748389-c3b9-496e-bcea-64883cff1e87'
_QUERY_VERSION = 102
_VARIABLES = {
    'opaqueImageFormat': 'JPG',
    'transparentImageFormat': 'PNG',
    'videoMerchEnabled': True,
    'fetchPromoVideoOverride': False,
    'hasPromoVideoOverride': True,
    'promoVideoId': 0,
    'videoMerchContext': 'BROWSE',
    'isLiveEpisodic': False,
    'includeCroppedLogo': False,
    'checkLinearChannel': True,
    'textEvidenceUiContext': 'ODP',
    'artworkContext': {},
}
_EMPTY = {'thumb': '', 'landscape': '', 'fanart': '', 'clearlogo': ''}


def _owner(node):
    video_id = node.get('videoId')
    if video_id is not None:
        return str(video_id)
    entity_id = node.get('unifiedEntityId')
    return str(entity_id).rsplit(':', 1)[-1] if entity_id is not None else ''


def _has_owner(node):
    if isinstance(node, dict):
        return bool(_owner(node)) or any(_has_owner(x) for x in node.values())
    if isinstance(node, list):
        return any(_has_owner(x) for x in node)
    return False


def _collect(node, owner, wanted, result):
    if isinstance(node, dict):
        owner = _owner(node) or owner
        if node.get('__typename') == 'Image' and (wanted is None or owner == wanted):
            result.append(node)
        for value in node.values():
            _collect(value, owner, wanted, result)
    elif isinstance(node, list):
        for value in node:
            _collect(value, owner, wanted, result)


def _valid_image_url(url):
    """Accept only HTTPS image URLs at expected Netflix/CDN domains."""
    if not isinstance(url, str) or len(url) > 4096:
        return False
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or '').lower()
    except ValueError:
        return False
    return parsed.scheme == 'https' and any(
        host == domain or host.endswith('.' + domain)
        for domain in ('nflxso.net', 'nflximg.net', 'netflix.com'))


def _pick(nodes, art_type, minimum_width=0):
    matches = []
    for node in nodes:
        if str(node.get('key') or '').split('|', 1)[0] != art_type:
            continue
        url = node.get('url')
        if node.get('available') is False or not _valid_image_url(url):
            continue
        try:
            width = int(node.get('width') or 0)
        except (TypeError, ValueError):
            width = 0
        if width >= minimum_width:
            matches.append((width, url))
    return max(matches, default=(0, ''))[1]


def extract_art(data, video_id):
    """Return artwork scoped to the requested video, not neighboring promos."""
    nodes = []
    _collect(data, None, str(video_id) if _has_owner(data) else None, nodes)
    preview = _pick(nodes, 'sdp', minimum_width=400)
    logo = (_pick(nodes, 'LOGO_BRANDED_HORIZONTAL') or
            _pick(nodes, 'LOGO_UNBRANDED_HORIZONTAL'))
    return dict(_EMPTY, thumb=preview, landscape=preview,
                fanart=_pick(nodes, 'StoryArt'), clearlogo=logo)


def fetch_art(session, video_id):
    """Use NFSession's post_safe; do not create/export a second cookie jar."""
    try:
        video_id = int(video_id)
        if video_id <= 0:
            return {'status': 'not_found', 'art': dict(_EMPTY)}
        variables = dict(_VARIABLES)
        variables.update({'videoId': video_id, 'unifiedEntityId': 'Video:{}'.format(video_id)})
        payload = {
            'operationName': 'DetailModal',
            'variables': variables,
            'extensions': {'persistedQuery': {'id': _QUERY_ID, 'version': _QUERY_VERSION}},
        }
        response = session.post_safe(endpoint='rnx_graphql_art', data=payload)
        if not isinstance(response, dict):
            return {'status': 'unavailable', 'art': dict(_EMPTY)}
        errors = response.get('errors')
        if errors:
            entries = errors if isinstance(errors, list) else [errors]
            is_unauthenticated = any(
                'unauthenticated' in str(
                    entry.get('message', '') if isinstance(entry, dict) else entry
                ).lower() for entry in entries)
            return {'status': 'unauthenticated' if is_unauthenticated else 'unavailable',
                    'art': dict(_EMPTY)}
        data = response.get('data')
        if not isinstance(data, dict):
            return {'status': 'unavailable', 'art': dict(_EMPTY)}
        return {'status': 'ok', 'art': extract_art(data, video_id)}
    except (TypeError, ValueError):
        return {'status': 'not_found', 'art': dict(_EMPTY)}
    except Exception as exc:  # pylint: disable=broad-except
        LOG.warn('Experimental GraphQL artwork unavailable ({})', type(exc).__name__)
        return {'status': 'unavailable', 'art': dict(_EMPTY)}
