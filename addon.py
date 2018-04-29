# -*- coding: utf-8 -*-
# Author: asciidisco
# Module: default
# Created on: 13.01.2017
# License: MIT https://goo.gl/5bMj3H

"""Kodi plugin for Netflix (https://netflix.com)"""


import sys
from resources.lib.NetflixCommon import NetflixCommon
from resources.lib.Navigation import Navigation

# Setup plugin
PLUGIN_HANDLE = int(sys.argv[1])
BASE_URL = sys.argv[0]
# We use string slicing to trim the leading ? from the plugin call paramstring
REQUEST_PARAMS = sys.argv[2][1:]

# init plugin libs
NETFLIX_COMMON = NetflixCommon(
    plugin_handle=PLUGIN_HANDLE,
    base_url=BASE_URL
)

NAVIGATION = Navigation(
    nx_common=NETFLIX_COMMON
)

if __name__ == '__main__':
    # Call the router function and pass the plugin call parameters to it.
    NETFLIX_COMMON.log('Started (Version ' + NETFLIX_COMMON.version + ')')
    NAVIGATION.router(paramstring=REQUEST_PARAMS)
