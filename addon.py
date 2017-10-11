# -*- coding: utf-8 -*-
# Author: asciidisco
# Module: default
# Created on: 13.01.2017
# License: MIT https://goo.gl/5bMj3H

"""Kodi plugin for Netflix (https://netflix.com)"""


import sys
from resources.lib.KodiHelper import KodiHelper
from resources.lib.Navigation import Navigation
from resources.lib.Library import Library

# Setup plugin
PLUGIN_HANDLE = int(sys.argv[1])
BASE_URL = sys.argv[0]
# We use string slicing to trim the leading ? from the plugin call paramstring
REQUEST_PARAMS = sys.argv[2][1:]

# init plugin libs
KODI_HELPER = KodiHelper(
    plugin_handle=PLUGIN_HANDLE,
    base_url=BASE_URL
)
LIBRARY = Library(
    root_folder=KODI_HELPER.base_data_path,
    library_settings=KODI_HELPER.get_custom_library_settings(),
    log_fn=KODI_HELPER.log
)
NAVIGATION = Navigation(
    kodi_helper=KODI_HELPER,
    library=LIBRARY,
    base_url=BASE_URL,
    log_fn=KODI_HELPER.log
)
KODI_HELPER.set_library(library=LIBRARY)

if __name__ == '__main__':
    # Call the router function and pass the plugin call parameters to it.
    KODI_HELPER.log('Started (Version ' + KODI_HELPER.version + ')')
    NAVIGATION.router(paramstring=REQUEST_PARAMS)
