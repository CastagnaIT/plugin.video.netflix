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

from resources.lib.globals import G
from resources.lib.utils.logging import LOG
from .misc_utils import is_less_version

__CURRENT_KODI_PROFILE_NAME__ = None

LOCALE_CONV_TABLE = {
    'es-ES': 'es-Spain',
    'pt-BR': 'pt-Brazil',
    'fr-CA': 'fr-Canada',
    'ar-EG': 'ar-Egypt',
    'nl-BE': 'nl-Belgium',
    'en-GB': 'en-UnitedKingdom'
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
    LOG.debug('Executing JSON-RPC: {}', request)
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
    LOG.debug('Executing JSON-RPC: {}', request)
    raw_response = xbmc.executeJSONRPC(request)
    if 'error' in raw_response:
        raise IOError('JSONRPC-Error {}'.format(raw_response))
    return json.loads(raw_response)


def container_refresh(use_delay=False):
    """Refresh the current container"""
    if use_delay:
        # When operations are performed in the Kodi library before call this method
        # can be necessary to apply a delay before run the refresh, otherwise the page does not refresh correctly
        # seems to be caused by a race condition with the Kodi library update (but i am not really sure)
        from time import sleep
        sleep(1)
    WndHomeProps[WndHomeProps.IS_CONTAINER_REFRESHED] = 'True'
    xbmc.executebuiltin('Container.Refresh')


def container_update(url, reset_history=False):
    """Update the current container"""
    func_str = 'Container.Update({},replace)' if reset_history else 'Container.Update({})'
    xbmc.executebuiltin(func_str.format(url))


def get_local_string(string_id):
    """Retrieve a localized string by its id"""
    src = xbmc if string_id < 30000 else G.ADDON
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
    xbmc.executebuiltin(G.py2_encode('PlayMedia({})'.format(media)))


def stop_playback():
    """Stop the running playback"""
    xbmc.executebuiltin('PlayerControl(Stop)')


def get_current_kodi_profile_name(no_spaces=True):
    """Lazily gets the name of the Kodi profile currently used"""
    if not hasattr(get_current_kodi_profile_name, 'cached'):
        name = json_rpc('Profiles.GetCurrentProfile', {'properties': ['thumbnail', 'lockmode']}).get('label', 'unknown')
        get_current_kodi_profile_name.cached = name.replace(' ', '_') if no_spaces else name
    return get_current_kodi_profile_name.cached


class _WndProps(object):  # pylint: disable=no-init
    """Read and write a property to the Kodi home window"""
    # Default Properties keys
    SERVICE_STATUS = 'service_status'
    """Return current service status"""
    IS_CONTAINER_REFRESHED = 'is_container_refreshed'
    """Return 'True' when container_refresh in kodi_ops.py is used by context menus, etc."""
    CURRENT_DIRECTORY = 'current_directory'
    """
    Return the name of the currently loaded directory (so the method name of directory.py class), otherwise:
    ['']       When the add-on is in his first run instance, so startup page
    ['root']   When add-on startup page is re-loaded (like refresh) or manually called
    Notice: In some cases the value may not be consistent example:
     - when you exit to Kodi home
     - external calls to the add-on while browsing the add-on
    """
    def __getitem__(self, key):
        try:
            # If you use multiple Kodi profiles you need to distinguish the property of current profile
            return G.WND_KODI_HOME.getProperty(G.py2_encode('netflix_{}_{}'.format(get_current_kodi_profile_name(),
                                                                                   key)))
        except Exception:  # pylint: disable=broad-except
            return ''

    def __setitem__(self, key, newvalue):
        # If you use multiple Kodi profiles you need to distinguish the property of current profile
        G.WND_KODI_HOME.setProperty(G.py2_encode('netflix_{}_{}'.format(get_current_kodi_profile_name(),
                                                                        key)),
                                    newvalue)


WndHomeProps = _WndProps()


def get_kodi_audio_language(iso_format=xbmc.ISO_639_1):
    """
    Return the audio language from Kodi settings
    WARNING: Based on Kodi player settings can also return values as: 'mediadefault', 'original'
    """
    audio_language = json_rpc('Settings.GetSettingValue', {'setting': 'locale.audiolanguage'})
    if audio_language['value'] in ['mediadefault', 'original']:
        return audio_language['value']
    return convert_language_iso(audio_language['value'], iso_format)


def get_kodi_subtitle_language(iso_format=xbmc.ISO_639_1):
    """Return the subtitle language from Kodi settings"""
    subtitle_language = json_rpc('Settings.GetSettingValue', {'setting': 'locale.subtitlelanguage'})
    if subtitle_language['value'] == 'forced_only':
        return subtitle_language['value']
    return convert_language_iso(subtitle_language['value'], iso_format)


def convert_language_iso(from_value, iso_format=xbmc.ISO_639_1):
    """
    Convert given value (English name or two/three letter code) to the specified format
    :param iso_format: specify the iso format (two letter code ISO_639_1 or three letter code ISO_639_2)
    """
    return xbmc.convertLanguage(G.py2_encode(from_value), iso_format)


def fix_locale_languages(data_list):
    """Replace all the languages with the country code because Kodi does not support IETF BCP 47 standard"""
    # Languages with the country code causes the display of wrong names in Kodi settings like
    # es-ES as 'Spanish-Spanish', pt-BR as 'Portuguese-Breton', nl-BE as 'Dutch-Belarusian', etc
    # and the impossibility to set them as the default audio/subtitle language
    for item in data_list:
        if item.get('isNoneTrack', False):
            continue
        if item['language'] == 'pt-BR' and not G.KODI_VERSION.is_less_version('18.7'):
            # Replace pt-BR with pb, is an unofficial ISO 639-1 Portuguese (Brazil) language code
            # has been added to Kodi 18.7 and Kodi 19.x PR: https://github.com/xbmc/xbmc/pull/17689
            item['language'] = 'pb'
        if len(item['language']) > 2:
            # Replace know locale with country
            # so Kodi will not recognize the modified country code and will show the string as it is
            if item['language'] in LOCALE_CONV_TABLE:
                item['language'] = LOCALE_CONV_TABLE[item['language']]
            else:
                LOG.error('fix_locale_languages: missing mapping conversion for locale "{}"'.format(item['language']))


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
