# -*- coding: utf-8 -*-
"""
    Copyright (C) 2019 Dag Wieers (@dagwieers) <dag@wieers.com>

    SPDX-License-Identifier: GPL-3.0-only
    See LICENSES/GPL-3.0-only.md for more information.
"""
# pylint: disable=missing-docstring

from __future__ import absolute_import, division, print_function, unicode_literals
import sys


xbmc = __import__('xbmc')
xbmcaddon = __import__('xbmcaddon')
xbmcgui = __import__('xbmcgui')
xbmcplugin = __import__('xbmcplugin')
xbmcvfs = __import__('xbmcvfs')

default = 'directory/root'

if len(sys.argv) > 1:
    path = sys.argv[1].lstrip('/') or default
else:
    path = default
uri = 'plugin://plugin.video.netflix/{path}'.format(path=path)
sys.argv = [uri, '0', '']


from resources.lib import run_addon  # pylint: disable=wrong-import-position
run_addon.g.init_globals(sys.argv)
run_addon.info('Started (Version {})'.format(run_addon.g.VERSION))
run_addon.info('URL is {}'.format(run_addon.g.URL))
if run_addon._check_valid_credentials():  # pylint: disable=protected-access
    run_addon.check_addon_upgrade()
    run_addon.g.initial_addon_configuration()
    run_addon.route(path.split('/'))
run_addon.g.CACHE.commit()
