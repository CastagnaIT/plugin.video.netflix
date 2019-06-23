# -*- coding: utf-8 -*-
"""Helper functions for Kodi operations"""
from __future__ import unicode_literals

import json

import xbmc

from resources.lib.globals import g

from .logging import debug

LIBRARY_PROPS = {
    'episode': ['title', 'plot', 'writer', 'playcount', 'director', 'season',
                'episode', 'originaltitle', 'showtitle', 'lastplayed', 'file',
                'resume', 'dateadded', 'art', 'userrating', 'firstaired'],
    'movie': ['title', 'genre', 'year', 'director', 'trailer',
              'tagline', 'plot', 'plotoutline', 'originaltitle', 'lastplayed',
              'playcount', 'writer', 'studio', 'mpaa', 'country',
              'imdbnumber', 'runtime', 'set', 'showlink', 'premiered',
              'top250', 'file', 'sorttitle', 'resume', 'setid', 'dateadded',
              'tag', 'art', 'userrating']
}


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
    debug('Executing JSON-RPC: {}'.format(request))
    raw_response = unicode(xbmc.executeJSONRPC(request), 'utf-8')
    # debug('JSON-RPC response: {}'.format(raw_response))
    response = json.loads(raw_response)
    if 'error' in response:
        raise IOError('JSONRPC-Error {}: {}'
                      .format(response['error']['code'],
                              response['error']['message']))
    return response['result']


def update_library_item_details(dbtype, dbid, details):
    """
    Update properties of an item in the Kodi library
    """
    method = 'VideoLibrary.Set{}Details'.format(dbtype.capitalize())
    params = {'{}id'.format(dbtype): dbid}
    params.update(details)
    return json_rpc(method, params)


def get_library_items(dbtype, filter=None):
    """Return a list of all items in the Kodi library that are of type
    dbtype (either movie or episode)"""
    method = 'VideoLibrary.Get{}s'.format(dbtype.capitalize())
    params = {'properties': ['file']}
    if filter:
        params.update({'filter': filter})
    return json_rpc(method, params)[dbtype + 's']


def get_library_item_details(dbtype, itemid):
    """Return details for an item from the Kodi library"""
    method = 'VideoLibrary.Get{}Details'.format(dbtype.capitalize())
    params = {
        dbtype + 'id': itemid,
        'properties': LIBRARY_PROPS[dbtype]}
    return json_rpc(method, params)[dbtype + 'details']


def scan_library(path=""):
    """Start a library scanning in a specified folder"""
    method = 'VideoLibrary.Scan'
    params = { 'directory': path }
    return json_rpc(method, params)


def refresh_container():
    """Refresh the current container"""
    xbmc.executebuiltin('Container.Refresh')


def get_local_string(string_id):
    """Retrieve a localized string by its id"""
    src = xbmc if string_id < 30000 else g.ADDON
    return src.getLocalizedString(string_id)


def run_plugin_action(path, block=False):
    """Create an action that can be run with xbmc.executebuiltin in order
    to run a Kodi plugin specified by path. If block is True (default=False),
    the execution of code will block until the called plugin has finished
    running."""
    return 'XBMC.RunPlugin({}, {})'.format(path, block)


def run_plugin(path, block=False):
    """Run a Kodi plugin specified by path. If block is True (default=False),
    the execution of code will block until the called plugin has finished
    running."""
    xbmc.executebuiltin(run_plugin_action(path, block))


def schedule_builtin(time, command, name='NetflixTask'):
    """Set an alarm to run builtin command after time has passed"""
    xbmc.executebuiltin('AlarmClock({},{},{},silent)'
                        .format(name, command, time))


def play_media(media):
    """Play a media in Kodi"""
    xbmc.executebuiltin('PlayMedia({})'.format(media))


def stop_playback():
    """Stop the running playback"""
    xbmc.executebuiltin('PlayerControl(Stop)')


def get_kodi_audio_language():
    """
    Return the audio language from Kodi settings
    """
    audio_language = json_rpc('Settings.GetSettingValue', {'setting': 'locale.audiolanguage'})
    audio_language = xbmc.convertLanguage(audio_language['value'].encode('utf-8'), xbmc.ISO_639_1)
    audio_language = audio_language if audio_language else xbmc.getLanguage(xbmc.ISO_639_1, False)
    return audio_language if audio_language else 'en'


def get_kodi_subtitle_language():
    """
    Return the subtitle language from Kodi settings
    """
    subtitle_language = json_rpc('Settings.GetSettingValue', {'setting': 'locale.subtitlelanguage'})
    if subtitle_language['value'] == 'forced_only':
        return subtitle_language['value']
    subtitle_language = xbmc.convertLanguage(subtitle_language['value'].encode('utf-8'), xbmc.ISO_639_1)
    subtitle_language = subtitle_language if subtitle_language else xbmc.getLanguage(xbmc.ISO_639_1, False)
    subtitle_language = subtitle_language if subtitle_language else 'en'
    return subtitle_language


def fix_locale_languages(data_list):
    """Replace locale code, Kodi does not understand the country code"""
    # Get all the ISO 639-1 codes (without country)
    locale_list_nocountry = []
    for item in data_list:
        if item.get('isNoneTrack', False):
            continue
        if len(item['language']) == 2 and not item['language'] in locale_list_nocountry:
            locale_list_nocountry.append(item['language'])
    # Replace the locale languages with country with a new one
    for item in data_list:
        if item.get('isNoneTrack', False):
            continue
        if len(item['language']) == 2:
            continue
        item['language'] = _adjust_locale(item['language'], item['language'][0:2] in locale_list_nocountry)


def _adjust_locale(locale_code, lang_code_without_country_exists):
    """
    Locale conversion helper
    Conversion table to prevent Kodi to display es-ES as Spanish - Spanish, pt-BR as Portuguese - Breton, and so on
    """
    locale_conversion_table = {
        'es-ES': 'es-Spain',
        'pt-BR': 'pt-Brazil',
        'fr-CA': 'fr-Canada',
        'ar-EG': 'ar-Egypt',
        'nl-BE': 'nl-Belgium'
    }
    language_code = locale_code[0:2]
    if not lang_code_without_country_exists:
        return language_code
    else:
        if locale_code in locale_conversion_table:
            return locale_conversion_table[locale_code]
        else:
            common.debug('AdjustLocale - missing mapping conversion for locale: {}'.format(locale_code))
            return locale_code
