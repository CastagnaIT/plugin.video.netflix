#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Module: default
# Created on: 13.01.2017

import sys
from resources.lib.KodiHelper import KodiHelper
from resources.lib.Navigation import Navigation
from resources.lib.Library import Library

# Setup plugin
plugin_handle = int(sys.argv[1])
base_url = sys.argv[0]

# init plugin libs
kodi_helper = KodiHelper(
    plugin_handle=plugin_handle,
    base_url=base_url
)
library = Library(
    root_folder=kodi_helper.base_data_path,
    library_settings=kodi_helper.get_custom_library_settings(),
    log_fn=kodi_helper.log
)
navigation = Navigation(
    kodi_helper=kodi_helper,
    library=library,
    base_url=base_url,
    log_fn=kodi_helper.log
)
kodi_helper.set_library(library=library)

if __name__ == '__main__':
    # Call the router function and pass the plugin call parameters to it.
    # We use string slicing to trim the leading '?' from the plugin call paramstring
    kodi_helper.log('started')
    navigation.router(paramstring=sys.argv[2][1:])
