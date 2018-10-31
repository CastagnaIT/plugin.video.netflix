# -*- coding: utf-8 -*-
"""Navigation handling"""
from __future__ import unicode_literals

import resources.lib.common as common


class InvalidPathError(Exception):
    """The requested path is invalid and could not be routed"""
    pass


def execute(executor_type, pathitems, params):
    """Execute an action as specified by the path"""
    try:
        executor = executor_type(params).__getattribute__(
            pathitems[0] if pathitems else 'root')
    except AttributeError:
        raise InvalidPathError('Unknown action {}'.format('/'.join(pathitems)))
    common.debug('Invoking action executor {}'.format(executor.__name__))
    executor(pathitems=pathitems)
