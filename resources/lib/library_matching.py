""" Utility functions to identify items in the Kodi library"""
from resources.lib.utils import json_rpc


def guess_episode(item, item_fb):
    """
    Tries to identify the episode in the Kodi library represented by the item.
    """
    resp = json_rpc('VideoLibrary.GetEpisodes',
                    {'properties': ['playcount', 'tvshowid',
                                    'showtitle', 'season',
                                    'episode']})
    return _first_match_or_none('episode', item, resp.get('episodes', []),
                                item_fb, _match_episode)


def guess_movie(item, item_fb):
    """
    Tries to identify the movie in the Kodi library represented by the item.
    """
    params = {'properties': ['playcount', 'year', 'title']}
    try:
        params['filter'] = {'year': item['year']}
    except (TypeError, KeyError):
        pass
    resp = json_rpc('VideoLibrary.GetMovies', params)
    return _first_match_or_none('movie', item, resp.get('movies', []),
                                item_fb, _match_movie)


def _get_safe_with_fallback(item, fallback, **kwargs):
    itemkey = kwargs.get('itemkey', 'title')
    fallbackkey = kwargs.get('fallbackkey', 'title')
    default = kwargs.get('default', '')
    try:
        return item.get(itemkey) or fallback.get(fallbackkey)
    except AttributeError:
        return default


def _first_match_or_none(mediatype, item, candidates, item_fb, match_fn):
    return next(({'dbtype': mediatype,
                  'dbid': candidate['{}id'.format(mediatype)],
                  'playcount': candidate['playcount']}
                 for candidate in candidates
                 if match_fn(item, candidate, item_fb)),
                None)


def _match_movie(item, movie, fallback_data):
    title = _get_safe_with_fallback(item, fallback_data)
    movie_meta = '%s (%d)' % (movie['label'], movie['year'])
    return movie_meta == title or movie['label'] in title


def _match_episode_explicitly(item, candidate):
    try:
        matches_show = (item.get('tvshowid') == candidate['tvshowid'] or
                        item.get('showtitle') == candidate['showtitle'])
        matches_season = item.get('season') == candidate['season']
        matches_episode = item.get('episode') == candidate['episode']
        return matches_show and matches_season and matches_episode
    except AttributeError:
        return False


def _match_episode_by_title(title, candidate):
    episode_meta = 'S%02dE%02d' % (candidate['season'],
                                   candidate['episode'])
    return candidate['showtitle'] in title and episode_meta in title


def _match_episode(item, candidate, item_fb):
    title = _get_safe_with_fallback(item, item_fb, itemkey='label')
    return (_match_episode_explicitly(item, candidate) or
            _match_episode_by_title(title, candidate))
