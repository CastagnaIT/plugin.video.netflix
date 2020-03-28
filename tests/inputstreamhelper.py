# -*- coding: utf-8 -*-
"""
    Copyright (C) 2019 Dag Wieers (@dagwieers) <dag@wieers.com>
    This file implements the inputstreamhelper module, either using stubs or alternative functionality

    SPDX-License-Identifier: GPL-3.0-only
    See LICENSES/GPL-3.0-only.md for more information.
"""
from __future__ import absolute_import, division, print_function, unicode_literals


class Helper:
    """A stub implementation of the inputstreamhelper Helper class"""

    def __init__(self, protocol, drm=None):  # pylint: disable=unused-argument
        """A stub constructor for the inputstreamhelper Helper class"""
        if protocol in ('mpd', 'ism', 'hls'):
            self.inputstream_addon = 'inputstream.adaptive'
        elif protocol == 'rtmp':
            self.inputstream_addon = 'inputstream.rtmp'
        else:
            raise Exception('UnsupportedProtocol')

    def check_inputstream(self):
        """A stub implementation of the inputstreamhelper Helper check_inputstream classmethod"""
