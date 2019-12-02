# -*- coding: utf-8 -*-
"""
    Copyright (C) 2019 Dag Wieers (@dagwieers) <dag@wieers.com>
    Extra functions for testing

    SPDX-License-Identifier: GPL-3.0-only
    See LICENSES/GPL-3.0-only.md for more information.
"""
from __future__ import absolute_import, division, print_function, unicode_literals
import sys
import os
import json
import xml.etree.ElementTree as ET
import polib


def kodi_to_ansi(string):
    """Convert Kodi format tags to ANSI codes"""
    if string is None:
        return None
    string = string.replace('[B]', '\033[1m')
    string = string.replace('[/B]', '\033[21m')
    string = string.replace('[I]', '\033[3m')
    string = string.replace('[/I]', '\033[23m')
    string = string.replace('[COLOR gray]', '\033[30;1m')
    string = string.replace('[COLOR red]', '\033[31m')
    string = string.replace('[COLOR green]', '\033[32m')
    string = string.replace('[COLOR yellow]', '\033[33m')
    string = string.replace('[COLOR blue]', '\033[34m')
    string = string.replace('[COLOR purple]', '\033[35m')
    string = string.replace('[COLOR cyan]', '\033[36m')
    string = string.replace('[COLOR white]', '\033[37m')
    string = string.replace('[/COLOR]', '\033[39;0m')
    return string


def uri_to_path(uri):
    """Shorten a plugin URI to just the path"""
    if uri is None:
        return None
    return ' \033[33m→ \033[34m%s\033[39;0m' % uri.replace('plugin://plugin.video.vrt.nu', '')


def read_addon_xml(path):
    """Parse the addon.xml and return an info dictionary"""
    info = dict(
        path='./',  # '/storage/.kodi/addons/plugin.video.vrt.nu',
        profile='special://userdata',  # 'special://profile/addon_data/plugin.video.vrt.nu/',
        type='xbmc.python.pluginsource',
    )

    tree = ET.parse(path)
    root = tree.getroot()

    info.update(root.attrib)  # Add 'id', 'name' and 'version'
    info['author'] = info.pop('provider-name')

    for child in root:
        if child.attrib.get('point') != 'xbmc.addon.metadata':
            continue
        for grandchild in child:
            # Handle assets differently
            if grandchild.tag == 'assets':
                for asset in grandchild:
                    info[asset.tag] = asset.text
                continue
            # Not in English ?  Drop it
            if grandchild.attrib.get('lang', 'en_GB') != 'en_GB':
                continue
            # Add metadata
            info[grandchild.tag] = grandchild.text

    return {info['name']: info}


def global_settings():
    """Use the global_settings file"""
    try:
        with open('test/userdata/global_settings.json') as f:
            settings = json.load(f)
    except OSError as e:
        print("Error using 'test/userdata/global_settings.json' : %s" % e, file=sys.stderr)
        settings = {
            'locale.language': 'resource.language.en_gb',
            'network.bandwidth': 0,
        }

    if 'PROXY_SERVER' in os.environ:
        settings['network.usehttpproxy'] = True
        settings['network.httpproxytype'] = 0
        print('Using proxy server from environment variable PROXY_SERVER')
        settings['network.httpproxyserver'] = os.environ.get('PROXY_SERVER')
        if 'PROXY_PORT' in os.environ:
            print('Using proxy server from environment variable PROXY_PORT')
            settings['network.httpproxyport'] = os.environ.get('PROXY_PORT')
        if 'PROXY_USERNAME' in os.environ:
            print('Using proxy server from environment variable PROXY_USERNAME')
            settings['network.httpproxyusername'] = os.environ.get('PROXY_USERNAME')
        if 'PROXY_PASSWORD' in os.environ:
            print('Using proxy server from environment variable PROXY_PASSWORD')
            settings['network.httpproxypassword'] = os.environ.get('PROXY_PASSWORD')
    return settings


def addon_settings():
    """Use the addon_settings file"""
    try:
        with open('test/userdata/addon_settings.json') as f:
            settings = json.load(f)
    except OSError as e:
        print("Error using 'test/userdata/addon_settings.json': %s" % e, file=sys.stderr)
        settings = {}

    # Read credentials from credentials.json
    try:
        with open('test/userdata/credentials.json') as f:
            settings.update(json.load(f))
    except (IOError, OSError) as e:
        if os.environ.get('NETFLIX_USERNAME') and os.environ.get('NETFLIX_PASSWORD'):
            print('Using credentials from the environment variables NETFLIX_USERNAME, NETFLIX_PASSWORD and NETFLIX_ESN')
            settings['username'] = os.environ.get('NETFLIX_USERNAME')
            settings['password'] = os.environ.get('NETFLIX_PASSWORD')
        if os.environ.get('NETFLIX_ESN'):
            settings['esn'] = os.environ.get('NETFLIX_ESN')
        if not settings.get('username') and not settings.get('password') or not settings.get('esn'):
            print("Error using 'test/userdata/credentials.json': %s" % e, file=sys.stderr)
    return settings


def import_language(language):
    """Process the language.po file"""
    return polib.pofile('resources/language/{language}/strings.po'.format(language=language))
