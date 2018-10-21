# -*- coding: utf-8 -*-
"""Navigation handling"""
from __future__ import unicode_literals

MODE_DIRECTORY = 'directory'
MODE_HUB = 'hub'
MODE_ACTION = 'action'
MODE_PLAY = 'play'

class InvalidPathError(Exception):
    """The requested path is invalid and could not be routed"""
    pass
