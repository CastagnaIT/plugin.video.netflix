# -*- coding: utf-8 -*-
"""Functions for Kodi library NFO creation"""
# We have to use only the metadata, as we can't be sure we access the cache.
# This implies actors or genres can't be added for now

from resources.lib.globals import g
import resources.lib.api.shakti as api
import resources.lib.cache as cache
import resources.lib.common as common

import xml.etree.ElementTree as ET

import xbmcvfs


def create_episode_nfo(episode, season, show):
    """Build NFO file for episode"""
    tags = {
        'title': episode.get('title',''),
        'showtitle': show.get('title',''),
        'season': str(season.get('seq','')),
        'episode': str(episode.get('seq','')),
        'plot': episode.get('synopsis',''),
        'runtime': str(episode.get('runtime',0)/60),
        'year': str(season.get('year','')),
        'id': str(episode.get('id',''))
        }

    root = _build_root_node('episodedetails', tags)
    _add_episode_thumb(root,episode)
    return root


def create_show_nfo(show):
    """Build NFO file for TV Show"""
    tags = {
        'title': show['title'],
        'showtitle': show['title'],
        'plot': show.get('synopsis',''),
        'id': str(show['id']),
        'mpaa': show.get('rating','')
        }

    root = _build_root_node('tvshow', tags)
    _add_poster(root, show)
    _add_fanart(root,show)
    return root


def create_movie_nfo(movie):
    tags = {
        'title': movie.get('title',''),
        'plot': movie.get('synopsis',''),
        'id': str(movie.get('id','')),
        'mpaa': movie.get('rating',''),
        'year': str(movie.get('year','')),
        'runtime': str(movie.get('runtime',0)/60),
        }

    root = _build_root_node('movie', tags)
    _add_poster(root, movie)
    _add_fanart(root, movie)
    common.debug(root)
    return root

def _add_episode_thumb(root, episode):
    try:
        url = episode['thumbs'][0]['url']
        thumbnail = ET.SubElement(root,'thumb')
        thumbnail.text = url
    except:
        common.debug('Couldn\'t find any thumbnail for episode')

def _add_poster(root, data):
    try:
        url = data['boxart'][0]['url']
        poster = ET.SubElement(root,'thumb',{'aspect': 'poster', 'language':''})
        poster.text = url
    except:
        common.debug('Couldn\'t find any poster for tvshow')


def _add_fanart(root, data):
    try:
        url = data['storyart'][0]['url']
        fanart = ET.SubElement(root,'fanart')
        thumb = ET.SubElement(fanart, 'thumb')
        thumb.text = url
    except:
        common.debug('Couldn\'t find any fanart for tvshow')


def _build_root_node(root_name,tags):
    root = ET.Element(root_name)
    for (k, v) in tags.items():
        if v:
            tag = ET.SubElement(root,k)
            tag.text = v
    return root

