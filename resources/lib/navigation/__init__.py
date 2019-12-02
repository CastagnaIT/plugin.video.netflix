# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Navigation handling

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import resources.lib.common as common


class InvalidPathError(Exception):
    """The requested path is invalid and could not be routed"""


def execute(executor_type, pathitems, params):
    """Execute an action as specified by the path"""
    try:
        executor = executor_type(params).__getattribute__(
            pathitems[0] if pathitems else 'root')
    except AttributeError:
        raise InvalidPathError('Unknown action {}'.format('/'.join(pathitems)))
    common.debug('Invoking action executor {}', executor.__name__)
    executor(pathitems=pathitems)
