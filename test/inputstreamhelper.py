# -*- coding: utf-8 -*-
# Copyright: (c) 2019, Dag Wieers (@dagwieers) <dag@wieers.com>
# GNU General Public License v3.0 (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
''' This file implements the inputstreamhelper module, either using stubs or alternative functionality '''

from __future__ import absolute_import, division, print_function, unicode_literals


class Helper:
    ''' A stub implementation of the inputstreamhelper Helper class '''

    def __init__(self, protocol, drm=None):  # pylint: disable=unused-argument
        ''' A stub constructor for the inputstreamhelper Helper class '''
        if protocol in ('mpd', 'ism', 'hls'):
            self.inputstream_addon = 'inputstream.adaptive'
        elif protocol == 'rtmp':
            self.inputstream_addon = 'inputstream.rtmp'
        else:
            raise Exception('UnsupportedProtocol')

    def check_inputstream(self):
        ''' A stub implementation of the inputstreamhelper Helper check_inputstream classmethod '''
