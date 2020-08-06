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
run_addon.G.init_globals(sys.argv)
run_addon.LOG.info('Started (Version {})'.format(run_addon.G.VERSION))
run_addon.LOG.info('URL is {}'.format(run_addon.G.URL))
if run_addon._check_valid_credentials():  # pylint: disable=protected-access
    if run_addon.check_addon_upgrade():
        from resources.lib.config_wizard import run_addon_configuration  # pylint: disable=wrong-import-position
        run_addon_configuration()
    run_addon.route(path.split('/'))
