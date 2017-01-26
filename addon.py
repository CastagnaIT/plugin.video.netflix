#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Module: default
# Created on: 13.01.2017

# import local classes
if __package__ is None:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from resources.lib.NetflixSession import NetflixSession
    from resources.lib.KodiHelper import KodiHelper
    from resources.lib.Navigation import Navigation
    from resources.lib.Library import Library
else:
    from .resources.lib.NetflixSession import NetflixSession
    from .resources.lib.KodiHelper import KodiHelper
    from .resources.lib.Navigation import Navigation
    from .resources.lib.Library import Library

# Setup plugin
plugin_handle = int(sys.argv[1])
base_url = sys.argv[0]

# init plugin libs
kodi_helper = KodiHelper(
    plugin_handle=plugin_handle,
    base_url=base_url
)
netflix_session = NetflixSession(
    cookie_path=kodi_helper.cookie_path,
    data_path=kodi_helper.data_path,
    log_fn=kodi_helper.log
)
library = Library(
    base_url=base_url,
    root_folder=kodi_helper.base_data_path,
    library_settings=kodi_helper.get_custom_library_settings(),
    log_fn=kodi_helper.log
)
navigation = Navigation(
    netflix_session=netflix_session,
    kodi_helper=kodi_helper,
    library=library,
    base_url=base_url,
    log_fn=kodi_helper.log
)
kodi_helper.set_library(library=library)

if __name__ == '__main__':
    # Call the router function and pass the plugin call parameters to it.
    # We use string slicing to trim the leading '?' from the plugin call paramstring
    navigation.router(paramstring=sys.argv[2][1:])
