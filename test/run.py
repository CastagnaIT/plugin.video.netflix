# -*- coding: utf-8 -*-
# Copyright: (c) 2019, Dag Wieers (@dagwieers) <dag@wieers.com>
# GNU General Public License v3.0 (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

# pylint: disable=missing-docstring

from __future__ import absolute_import, division, print_function, unicode_literals
import sys


xbmc = __import__('xbmc')
xbmcaddon = __import__('xbmcaddon')
xbmcgui = __import__('xbmcgui')
xbmcplugin = __import__('xbmcplugin')
xbmcvfs = __import__('xbmcvfs')

default = '/mainmenu'

if len(sys.argv) > 1:
    path = sys.argv[1] or default
else:
    path = default
uri = 'plugin://plugin.video.netflix{path}'.format(path=path)
sys.argv = [uri, '0', '']


import addon
addon.g.init_globals(sys.argv)
addon.common.info('Started (Version {})'.format(addon.g.VERSION))
addon.common.info('URL is {}'.format(addon.g.URL))
if addon.check_valid_credentials():
    addon.upgrade_ctrl.check_addon_upgrade()
    addon.g.initial_addon_configuration()
    addon.route(path.split('/'))
addon.g.CACHE.commit()
