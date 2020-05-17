# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Helper functions for Kodi operations

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import json

import xbmc

from resources.lib.globals import g
from .misc_utils import is_less_version
from .logging import debug


LIBRARY_PROPS = {
    'episode': ['title', 'plot', 'writer', 'playcount', 'director', 'season',
                'episode', 'originaltitle', 'showtitle', 'lastplayed', 'file',
                'resume', 'dateadded', 'art', 'userrating', 'firstaired', 'runtime'],
    'movie': ['title', 'genre', 'year', 'director', 'trailer',
              'tagline', 'plot', 'plotoutline', 'originaltitle', 'lastplayed',
              'playcount', 'writer', 'studio', 'mpaa', 'country',
              'imdbnumber', 'runtime', 'set', 'showlink', 'premiered',
              'top250', 'file', 'sorttitle', 'resume', 'setid', 'dateadded',
              'tag', 'art', 'userrating']
}

__CURRENT_KODI_PROFILE_NAME__ = None


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
    debug('Executing JSON-RPC: {}', request)
    raw_response = xbmc.executeJSONRPC(request)
    # debug('JSON-RPC response: {}'.format(raw_response))
    response = json.loads(raw_response)
    if 'error' in response:
        raise IOError('JSONRPC-Error {}: {}'
                      .format(response['error']['code'],
                              response['error']['message']))
    return response['result']


def json_rpc_multi(method, list_params=None):
    """
    Executes multiple JSON-RPC with the same method in Kodi

    :param method: The JSON-RPC method to call
    :type method: string
    :param list_params: Multiple list of parameters of the method call
    :type list_params: a list of dict
    :returns: dict -- Method call result
    """
    request_data = [{'jsonrpc': '2.0', 'method': method, 'id': 1, 'params': params or {}} for params in list_params]
    request = json.dumps(request_data)
    debug('Executing JSON-RPC: {}', request)
    raw_response = xbmc.executeJSONRPC(request)
    if 'error' in raw_response:
        raise IOError('JSONRPC-Error {}'.format(raw_response))
    return json.loads(raw_response)


def update_library_item_details(dbtype, dbid, details):
    """Update properties of an item in the Kodi library"""
    method = 'VideoLibrary.Set{}Details'.format(dbtype.capitalize())
    params = {'{}id'.format(dbtype): dbid}
    params.update(details)
    return json_rpc(method, params)


def get_library_items(dbtype, video_filter=None):
    """Return a list of all items in the Kodi library that are of type dbtype (either movie or episode)"""
    method = 'VideoLibrary.Get{}s'.format(dbtype.capitalize())
    params = {'properties': ['file']}
    if video_filter:
        params.update({'filter': video_filter})
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
    params = {'directory': path}
    return json_rpc(method, params)


def refresh_container(use_delay=False):
    """Refresh the current container"""
    if use_delay:
        # When operations are performed in the Kodi library before call this method
        # can be necessary to apply a delay before run the refresh, otherwise the page does not refresh correctly
        # seems to be caused by a race condition with the Kodi library update (but i am not really sure)
        from time import sleep
        sleep(1)
    xbmc.executebuiltin('Container.Refresh')


def get_local_string(string_id):
    """Retrieve a localized string by its id"""
    src = xbmc if string_id < 30000 else g.ADDON
    return src.getLocalizedString(string_id)


def run_plugin_action(path, block=False):
    """Create an action that can be run with xbmc.executebuiltin in order to run a Kodi plugin specified by path.
    If block is True (default=False), the execution of code will block until the called plugin has finished running."""
    return 'RunPlugin({}, {})'.format(path, block)


def run_plugin(path, block=False):
    """Run a Kodi plugin specified by path. If block is True (default=False),
    the execution of code will block until the called plugin has finished running."""
    xbmc.executebuiltin(run_plugin_action(path, block))


def schedule_builtin(time, command, name='NetflixTask'):
    """Set an alarm to run builtin command after time has passed"""
    xbmc.executebuiltin('AlarmClock({},{},{},silent)'
                        .format(name, command, time))


def play_media(media):
    """Play a media in Kodi"""
    xbmc.executebuiltin(g.py2_encode('PlayMedia({})'.format(media)))


def stop_playback():
    """Stop the running playback"""
    xbmc.executebuiltin('PlayerControl(Stop)')


def get_current_kodi_profile_name(no_spaces=True):
    """Lazily gets the name of the Kodi profile currently used"""
    # pylint: disable=global-statement
    global __CURRENT_KODI_PROFILE_NAME__
    if not __CURRENT_KODI_PROFILE_NAME__:
        name = json_rpc('Profiles.GetCurrentProfile', {'properties': ['thumbnail', 'lockmode']}).get('label', 'unknown')
        __CURRENT_KODI_PROFILE_NAME__ = name.replace(' ', '_') if no_spaces else name
    return __CURRENT_KODI_PROFILE_NAME__


def get_kodi_audio_language():
    """Return the audio language from Kodi settings"""
    audio_language = json_rpc('Settings.GetSettingValue', {'setting': 'locale.audiolanguage'})
    return convert_language_iso(audio_language['value'])


def get_kodi_subtitle_language():
    """Return the subtitle language from Kodi settings"""
    subtitle_language = json_rpc('Settings.GetSettingValue', {'setting': 'locale.subtitlelanguage'})
    if subtitle_language['value'] == 'forced_only':
        return subtitle_language['value']
    return convert_language_iso(subtitle_language['value'])


def convert_language_iso(from_value, use_fallback=True):
    """
    Convert language code from an English name or three letter code (ISO 639-2) to two letter code (ISO 639-1)

    :param use_fallback: if True when the conversion fails, is returned the current Kodi active language
    """
    converted_lang = xbmc.convertLanguage(g.py2_encode(from_value), xbmc.ISO_639_1)
    if not use_fallback:
        return converted_lang
    converted_lang = converted_lang if converted_lang else xbmc.getLanguage(xbmc.ISO_639_1, False)
    return converted_lang if converted_lang else 'en'


def fix_locale_languages(data_list):
    """Replace locale code, Kodi does not understand the country code"""
    # Get all the ISO 639-1 codes (without country)
    verify_unofficial_lang = g.KODI_VERSION.is_major_ver('19') or not g.KODI_VERSION.is_less_version('18.7')
    locale_list_nocountry = []
    for item in data_list:
        if item.get('isNoneTrack', False):
            continue
        if verify_unofficial_lang and item['language'] == 'pt-BR':
            # Unofficial ISO 639-1 Portuguese (Brazil) language code has been added to Kodi 18.7 and Kodi 19.x
            # https://github.com/xbmc/xbmc/pull/17689
            item['language'] = 'pb'
        if len(item['language']) == 2 and not item['language'] in locale_list_nocountry:
            locale_list_nocountry.append(item['language'])
    # Replace the locale languages with country with a new one
    for item in data_list:
        if item.get('isNoneTrack', False):
            continue
        if len(item['language']) == 2:
            continue
        item['language'] = _adjust_locale(item['language'],
                                          item['language'][0:2] in locale_list_nocountry)


def _adjust_locale(locale_code, lang_code_without_country_exists):
    """
    Locale conversion helper
    Conversion table to prevent Kodi to display
    es-ES as Spanish - Spanish, pt-BR as Portuguese - Breton, and so on
    Kodi issue: https://github.com/xbmc/xbmc/issues/15308
    """
    locale_conversion_table = {
        'es-ES': 'es-Spain',
        'pt-BR': 'pt-Brazil',
        'fr-CA': 'fr-Canada',
        'ar-EG': 'ar-Egypt',
        'nl-BE': 'nl-Belgium',
        'en-GB': 'en-UnitedKingdom'
    }
    language_code = locale_code[0:2]
    if not lang_code_without_country_exists:
        return language_code

    if locale_code in locale_conversion_table:
        return locale_conversion_table[locale_code]

    debug('AdjustLocale - missing mapping conversion for locale: {}'.format(locale_code))
    return locale_code


class GetKodiVersion(object):
    """Get the kodi version, git date, stage name"""
    # Examples of some types of supported strings:
    # 10.1 Git:Unknown                       PRE-11.0 Git:Unknown                  11.0-BETA1 Git:20111222-22ad8e4
    # 18.1-RC1 Git:20190211-379f5f9903       19.0-ALPHA1 Git:20190419-c963b64487
    def __init__(self):
        import re
        self.build_version = xbmc.getInfoLabel('System.BuildVersion')
        # Parse the version number
        result = re.search(r'\d+\.\d+', self.build_version)
        self.version = result.group(0) if result else ''
        # Parse the major version number
        self.major_version = self.version.split('.')[0] if self.version else ''
        # Parse the date of GIT build
        result = re.search(r'(Git:)(\d+?(?=(-|$)))', self.build_version)
        self.date = int(result.group(2)) if result and len(result.groups()) >= 2 else None
        # Parse the stage name
        result = re.search(r'(\d+\.\d+-)(.+)(?=\s)', self.build_version)
        if not result:
            result = re.search(r'^(.+)(-\d+\.\d+)', self.build_version)
            self.stage = result.group(1) if result else ''
        else:
            self.stage = result.group(2) if result else ''

    def is_major_ver(self, major_ver):
        return bool(major_ver in self.major_version)

    def is_less_version(self, ver):
        return is_less_version(self.version, ver)

    def __str__(self):
        return self.build_version
