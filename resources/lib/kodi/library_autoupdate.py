# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT
    Kodi library integration: library auto-update, auto-sync

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import random
from datetime import datetime, timedelta

import xbmc

import resources.lib.common as common
import resources.lib.kodi.nfo as nfo
import resources.lib.kodi.ui as ui
from resources.lib.database.db_utils import (VidLibProp)
from resources.lib.globals import g
from resources.lib.kodi.library import (export_new_episodes, execute_library_tasks_silently,
                                        execute_library_tasks)
from resources.lib.kodi.library_items import export_item, remove_item

try:  # Python 2
    unicode
except NameError:  # Python 3
    unicode = str  # pylint: disable=redefined-builtin


def show_excluded_from_auto_update(videoid):
    """Return true if the videoid is excluded from auto-update"""
    return g.SHARED_DB.get_tvshow_property(videoid.value, VidLibProp['exclude_update'], False)


def exclude_show_from_auto_update(videoid, exclude):
    """Set if a tvshow is excluded from auto-update"""
    g.SHARED_DB.set_tvshow_property(videoid.value, VidLibProp['exclude_update'], exclude)


def auto_update_library(sync_with_mylist, silent):
    """
    Perform an auto update of the exported items to Kodi library,
    so check if there is new seasons/episodes.
    If sync_with_mylist is enabled the Kodi library will be also synchronized
    with the Netflix "My List".
    :param sync_with_mylist: True to enable sync with My List
    :param silent: don't display user interface while performing an operation
    :return: None
    """
    if _is_auto_update_library_running():
        return
    execute_lib_tasks_method = execute_library_tasks_silently if silent else execute_library_tasks
    common.info(
        'Starting auto update library - check updates for tv shows (sync with My List is {})',
        'ENABLED' if sync_with_mylist else 'DISABLED')
    g.SHARED_DB.set_value('library_auto_update_is_running', True)
    g.SHARED_DB.set_value('library_auto_update_start_time', datetime.now())
    try:
        videoids_to_update = []

        # Get the list of the exported items to Kodi library
        exported_tvshows_videoids_values = g.SHARED_DB.get_tvshows_id_list()
        exported_movies_videoids_values = g.SHARED_DB.get_movies_id_list()

        if sync_with_mylist:
            # Get My List videoids of the chosen profile
            # Use make_http_call instead make_http because call AddonSignals on same instance makes problems
            mylist_video_id_list, mylist_video_id_list_type = common.make_http_call(
                'get_mylist_videoids_profile_switch', None)

            # Check if tv shows have been removed from the My List
            for videoid_value in exported_tvshows_videoids_values:
                if unicode(videoid_value) in mylist_video_id_list:
                    continue
                # The tv show no more exist in My List so remove it from library
                videoid = common.VideoId.from_path([common.VideoId.SHOW, videoid_value])
                execute_lib_tasks_method(videoid, [remove_item])

            # Check if movies have been removed from the My List
            for videoid_value in exported_movies_videoids_values:
                if unicode(videoid_value) in mylist_video_id_list:
                    continue
                # The movie no more exist in My List so remove it from library
                videoid = common.VideoId.from_path([common.VideoId.MOVIE, videoid_value])
                execute_lib_tasks_method(videoid, [remove_item])

            # Add missing tv shows / movies of My List to library
            for index, video_id in enumerate(mylist_video_id_list):
                if (int(video_id) not in exported_tvshows_videoids_values and
                        int(video_id) not in exported_movies_videoids_values):
                    videoids_to_update.append(
                        common.VideoId(
                            **{('movieid' if (mylist_video_id_list_type[index] == 'movie') else 'tvshowid'): video_id}))

        # Add the exported tv shows to be updated to the list..
        tvshows_videoids_to_upd = [
            common.VideoId.from_path([common.VideoId.SHOW, videoid_value]) for
            videoid_value in g.SHARED_DB.get_tvshows_id_list(VidLibProp['exclude_update'], False)
        ]
        # ..and avoids any duplication caused by possible unexpected errors
        videoids_to_update.extend(list(set(tvshows_videoids_to_upd) - set(videoids_to_update)))

        # Add missing tv shows/movies or update existing tv shows
        _update_library(videoids_to_update, exported_tvshows_videoids_values, silent)

        common.debug('Auto update of the library completed')
        g.SHARED_DB.set_value('library_auto_update_is_running', False)
        if not g.ADDON.getSettingBool('lib_auto_upd_disable_notification'):
            ui.show_notification(common.get_local_string(30220), time=5000)
        common.debug('Notify service to communicate to Kodi of update the library')
        common.send_signal(common.Signals.LIBRARY_UPDATE_REQUESTED)
    except Exception:  # pylint: disable=broad-except
        import traceback
        common.error('An error has occurred in the library auto update')
        common.error(g.py2_decode(traceback.format_exc(), 'latin-1'))
        g.SHARED_DB.set_value('library_auto_update_is_running', False)


def _is_auto_update_library_running():
    update = g.SHARED_DB.get_value('library_auto_update_is_running', False)
    if update:
        start_time = g.SHARED_DB.get_value('library_auto_update_start_time',
                                           datetime.utcfromtimestamp(0))
        if datetime.now() >= start_time + timedelta(hours=6):
            g.SHARED_DB.set_value('library_auto_update_is_running', False)
            common.warn('Canceling previous library update: duration >6 hours')
        else:
            common.debug('Library auto update is already running')
            return True
    return False


def _update_library(videoids_to_update, exported_tvshows_videoids_values, silent):
    execute_lib_tasks_method = execute_library_tasks_silently if silent else execute_library_tasks
    # Get the list of the Tv Shows exported to exclude from updates
    excluded_videoids_values = g.SHARED_DB.get_tvshows_id_list(VidLibProp['exclude_update'], True)
    for videoid in videoids_to_update:
        # Check if current videoid is excluded from updates
        if int(videoid.value) in excluded_videoids_values:
            continue
        if int(videoid.value) in exported_tvshows_videoids_values:
            # It is possible that the user has chosen not to export NFO files for a tv show
            nfo_export = g.SHARED_DB.get_tvshow_property(videoid.value,
                                                         VidLibProp['nfo_export'], False)
            nfo_settings = nfo.NFOSettings(nfo_export)
        else:
            nfo_settings = nfo.NFOSettings()
        if videoid.mediatype == common.VideoId.SHOW:
            export_new_episodes(videoid, silent, nfo_settings)
        if videoid.mediatype == common.VideoId.MOVIE:
            execute_lib_tasks_method(videoid, [export_item], nfo_settings=nfo_settings)
        # Add some randomness between operations to limit servers load and ban risks
        xbmc.sleep(random.randint(1000, 5001))
