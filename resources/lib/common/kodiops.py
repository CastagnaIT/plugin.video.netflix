# -*- coding: utf-8 -*-
"""Helper functions for Kodi operations"""
from __future__ import unicode_literals

import json

import xbmc

from .globals import ADDON


def find_season(season_id, seasons, raise_exc=True):
    """
    Get metadata for a specific season from within a nested
    metadata dict.
    :return: Season metadata. Raises KeyError if metadata for season_id
    does not exist.
    """
    for season in seasons:
        if str(season['id']) == season_id:
            return season
    if raise_exc:
        raise KeyError('Metadata for season {} does not exist'
                       .format(season_id))
    else:
        return {}


def find_episode(episode_id, seasons, raise_exc=True):
    """
    Get metadata for a specific episode from within a nested
    metadata dict.
    :return: Episode metadata. Raises KeyError if metadata for episode_id
    does not exist.
    """
    for season in seasons:
        for episode in season['episodes']:
            if str(episode['id']) == episode_id:
                return episode
    if raise_exc:
        raise KeyError('Metadata for episode {} does not exist'
                       .format(episode_id))
    else:
        return {}


def update_library_item_details(dbtype, dbid, details):
    """
    Update properties of an item in the Kodi library
    """
    method = 'VideoLibrary.Set{}Details'.format(dbtype.capitalize())
    params = {'{}id'.format(dbtype): dbid}
    params.update(details)
    return json_rpc(method, params)


def json_rpc(method, params=None):
    """
    Executes a JSON-RPC in Kodi

    :param method: The JSON-RPC method to call
    :type method: string
    :param params: The parameters of the method call (optional)
    :type params: dict
    :returns: dict -- Method call result
    """
    request_data = {'jsonrpc': '2.0', 'method': method, 'id': 1,
                    'params': params or {}}
    request = json.dumps(request_data)
    response = json.loads(unicode(xbmc.executeJSONRPC(request), 'utf-8',
                                  errors='ignore'))
    if 'error' in response:
        raise IOError('JSONRPC-Error {}: {}'
                      .format(response['error']['code'],
                              response['error']['message']))
    return response['result']


def refresh_container():
    """Refresh the current container"""
    xbmc.executebuiltin('Container.Refresh')


def get_local_string(string_id):
    """Retrieve a localized string by its id"""
    src = xbmc if string_id < 30000 else ADDON
    return src.getLocalizedString(string_id)
