# -*- coding: utf-8 -*-
"""Experimental cached artwork enrichment for Kodi list items.

Uses a distinct persistent cache key (per video, profile and language) and
limits synchronous GraphQL lookups to keep menu latency bounded.
This proof of concept still needs a non-blocking/batched upstream design.
"""
import resources.lib.common as common
from resources.lib.common.cache_utils import CACHE_ARTINFO
from resources.lib.common.exceptions import CacheMiss
from resources.lib.globals import G
from resources.lib.utils.logging import LOG

_ART_KEYS = ('fanart', 'landscape', 'thumb', 'clearlogo')
_MAX_NEW_REQUESTS_PER_MENU = 12
_ATTEMPTS = 0
_CIRCUIT_OPEN = False


def _combine(original, additional):
    art = dict(original)
    for name in _ART_KEYS:
        value = additional.get(name)
        if value:
            art[name] = value
    return art


def enrich_art(videoid, original, language=''):
    """Return original artwork on any GraphQL error, without interrupting browsing."""
    global _ATTEMPTS, _CIRCUIT_OPEN
    try:
        number = int(videoid.value)
        if number <= 0:
            return original
    except (TypeError, ValueError, AttributeError):
        return original

    # Keep separate image sets for Netflix profiles with different languages.
    try:
        profile = G.LOCAL_DB.get_active_profile_guid() or ''
    except Exception:  # pylint: disable=broad-except
        profile = ''
    cache_key = 'rnx_graphql_v1_{}_{}_{}'.format(profile, number, language or '')
    try:
        result = G.CACHE.get(CACHE_ARTINFO, cache_key)
    except CacheMiss:
        if _CIRCUIT_OPEN or _ATTEMPTS >= _MAX_NEW_REQUESTS_PER_MENU:
            return original
        _ATTEMPTS += 1
        try:
            result = common.make_call('rnx_graphql_art', {'video_id': number})
        except Exception as exc:  # pylint: disable=broad-except
            LOG.warn('Experimental artwork IPC failed ({})', type(exc).__name__)
            _CIRCUIT_OPEN = True
            return original
        if not isinstance(result, dict):
            _CIRCUIT_OPEN = True
            return original
        status = result.get('status')
        if status != 'ok':
            if status in ('unauthenticated', 'unavailable'):
                _CIRCUIT_OPEN = True
            try:
                G.CACHE.add(CACHE_ARTINFO, cache_key,
                            {'status': status, 'art': {}}, ttl=1800,
                            delayed_db_op=True)
            except Exception:  # pylint: disable=broad-except
                pass
            return original
        try:
            G.CACHE.add(CACHE_ARTINFO, cache_key, result,
                        ttl=7 * 24 * 3600, delayed_db_op=True)
        except Exception as exc:  # pylint: disable=broad-except
            LOG.warn('Experimental artwork cache write failed ({})', type(exc).__name__)
    except Exception as exc:  # pylint: disable=broad-except
        LOG.warn('Experimental artwork cache read failed ({})', type(exc).__name__)
        return original

    if result.get('status') != 'ok':
        return original
    return _combine(original, result.get('art') or {})
