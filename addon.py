# -*- coding: utf-8 -*-
# Author: asciidisco
# Module: default
# Created on: 13.01.2017
# License: MIT https://goo.gl/5bMj3H

"""Kodi plugin for Netflix (https://netflix.com)"""
from __future__ import unicode_literals

import sys
import resources.lib.common as common
from resources.lib.Navigation import Navigation

# We use string slicing to trim the leading ? from the plugin call paramstring
REQUEST_PARAMS = sys.argv[2][1:]

if __name__ == '__main__':
    # Call the router function and pass the plugin call parameters to it.
    common.log('Started (Version {})'.format(common.VERSION), common.LOGINFO)
    Navigation().router(paramstring=REQUEST_PARAMS)
