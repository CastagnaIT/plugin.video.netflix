# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Navigation handler for actions

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import xbmc

import resources.lib.utils.api_requests as api
import resources.lib.common as common
import resources.lib.kodi.ui as ui
from resources.lib.utils.exceptions import MissingCredentialsError, CacheMiss
from resources.lib.utils.api_paths import VIDEO_LIST_RATING_THUMB_PATHS, SUPPLEMENTAL_TYPE_TRAILERS
from resources.lib.common import cache_utils
from resources.lib.globals import G
from resources.lib.kodi.library import get_library_cls


class AddonActionExecutor(object):
    """Executes actions"""
    # pylint: disable=no-self-use
    def __init__(self, params):
        common.debug('Initializing "AddonActionExecutor" with params: {}', params)
        self.params = params

    def logout(self, pathitems=None):  # pylint: disable=unused-argument
        """Perform account logout"""
        api.logout()

    def autoselect_profile_set(self, pathitems):  # pylint: disable=unused-argument
        """Save the GUID for profile auto-selection"""
        G.LOCAL_DB.set_value('autoselect_profile_guid', self.params['profile_guid'])
        G.settings_monitor_suspend(True)
        G.ADDON.setSetting('autoselect_profile_name', self.params['profile_name'])
        G.ADDON.setSettingBool('autoselect_profile_enabled', True)
        G.settings_monitor_suspend(False)
        ui.show_notification(common.get_local_string(30058).format(G.py2_decode(self.params['profile_name'])))

    def autoselect_profile_remove(self, pathitems):  # pylint: disable=unused-argument
        """Remove the auto-selection set"""
        G.LOCAL_DB.set_value('autoselect_profile_guid', '')
        G.settings_monitor_suspend(True)
        G.ADDON.setSetting('autoselect_profile_name', '')
        G.ADDON.setSettingBool('autoselect_profile_enabled', False)
        G.settings_monitor_suspend(False)

    def library_playback_profile(self, pathitems=None):  # pylint: disable=unused-argument
        preselect_guid = G.LOCAL_DB.get_value('library_playback_profile_guid')
        selected_guid = ui.show_profiles_dialog(title=common.get_local_string(30050),
                                                preselect_guid=preselect_guid)
        if not selected_guid:
            return
        # Save the selected profile guid
        G.LOCAL_DB.set_value('library_playback_profile_guid', selected_guid)
        # Save the selected profile name
        G.ADDON.setSetting('library_playback_profile', G.LOCAL_DB.get_profile_config('profileName', '???',
                                                                                     guid=selected_guid))

    def parental_control(self, pathitems=None):  # pylint: disable=unused-argument
        """Open parental control settings dialog"""
        password = ui.ask_for_password()
        if not password:
            return
        try:
            parental_control_data = api.get_parental_control_data(password)
            ui.show_modal_dialog(False,
                                 ui.xmldialogs.ParentalControl,
                                 'plugin-video-netflix-ParentalControl.xml',
                                 G.ADDON.getAddonInfo('path'),
                                 **parental_control_data)
        except MissingCredentialsError:
            ui.show_ok_dialog('Netflix', common.get_local_string(30009))

    @common.inject_video_id(path_offset=1)
    @common.time_execution(immediate=False)
    def rate_thumb(self, videoid):
        """Rate an item on Netflix. Ask for a thumb rating"""
        # Get updated user rating info for this videoid
        raw_data = api.get_video_raw_data([videoid], VIDEO_LIST_RATING_THUMB_PATHS)
        if raw_data.get('videos', {}).get(videoid.value):
            video_data = raw_data['videos'][videoid.value]
            title = video_data.get('title')
            track_id_jaw = video_data.get('trackIds', {})['trackId_jaw']
            is_thumb_rating = video_data.get('userRating', {}).get('type', '') == 'thumb'
            user_rating = video_data.get('userRating', {}).get('userRating') if is_thumb_rating else None
            ui.show_modal_dialog(False,
                                 ui.xmldialogs.RatingThumb,
                                 'plugin-video-netflix-RatingThumb.xml',
                                 G.ADDON.getAddonInfo('path'),
                                 videoid=videoid,
                                 title=title,
                                 track_id_jaw=track_id_jaw,
                                 user_rating=user_rating)
        else:
            common.warn('Rating thumb video list api request no got results for {}', videoid)

    # Old rating system
    # @common.inject_video_id(path_offset=1)
    # @common.time_execution(immediate=False)
    # def rate(self, videoid):
    #     """Rate an item on Netflix. Ask for a rating if there is none supplied
    #     in the path."""
    #     rating = self.params.get('rating') or ui.ask_for_rating()
    #     if rating is not None:
    #         api.rate(videoid, rating)

    @common.inject_video_id(path_offset=2, inject_remaining_pathitems=True)
    @common.time_execution(immediate=False)
    def my_list(self, videoid, pathitems):
        """Add or remove an item from my list"""
        operation = pathitems[1]
        api.update_my_list(videoid, operation, self.params)
        _sync_library(videoid, operation)
        common.container_refresh()

    @common.inject_video_id(path_offset=1)
    @common.time_execution(immediate=False)
    def trailer(self, videoid):
        """Get the trailer list"""
        from json import dumps
        menu_data = {'path': ['is_context_menu_item', 'is_context_menu_item'],  # Menu item do not exists
                     'title': common.get_local_string(30179)}
        video_id_dict = videoid.to_dict()
        list_data, extra_data = common.make_call('get_video_list_supplemental',  # pylint: disable=unused-variable
                                                 {
                                                     'menu_data': menu_data,
                                                     'video_id_dict': video_id_dict,
                                                     'supplemental_type': SUPPLEMENTAL_TYPE_TRAILERS
                                                 })
        if list_data:
            url = common.build_url(['supplemental'],
                                   params={'video_id_dict': dumps(video_id_dict),
                                           'supplemental_type': SUPPLEMENTAL_TYPE_TRAILERS},
                                   mode=G.MODE_DIRECTORY)
            common.container_update(url)
        else:
            ui.show_notification(common.get_local_string(30111))

    @common.time_execution(immediate=False)
    def purge_cache(self, pathitems=None):  # pylint: disable=unused-argument
        """Clear the cache. If on_disk param is supplied, also clear cached items from disk"""
        G.CACHE.clear(clear_database=self.params.get('on_disk', False))
        ui.show_notification(common.get_local_string(30135))

    def force_update_list(self, pathitems=None):  # pylint: disable=unused-argument
        """Clear the cache of my list to force the update"""
        if self.params['menu_id'] == 'myList':
            G.CACHE.clear([cache_utils.CACHE_MYLIST], clear_database=False)
        if self.params['menu_id'] == 'continueWatching':
            # Delete the cache of continueWatching list
            # pylint: disable=unused-variable
            is_exists, list_id = common.make_call('get_continuewatching_videoid_exists', {'video_id': ''})
            if list_id:
                G.CACHE.delete(cache_utils.CACHE_COMMON, list_id, including_suffixes=True)
            # When the continueWatching context is invalidated from a refreshListByContext call
            # the LoCo need to be updated to obtain the new list id, so we delete the cache to get new data
            G.CACHE.delete(cache_utils.CACHE_COMMON, 'loco_list')

    def view_esn(self, pathitems=None):  # pylint: disable=unused-argument
        """Show the ESN in use"""
        ui.show_ok_dialog(common.get_local_string(30016), G.get_esn())

    def reset_esn(self, pathitems=None):  # pylint: disable=unused-argument
        """Reset the ESN stored (retrieved from website and manual)"""
        from resources.lib.database.db_utils import (TABLE_SESSION, TABLE_SETTINGS_MONITOR)
        if not ui.ask_for_confirmation(common.get_local_string(30217),
                                       common.get_local_string(30218)):
            return
        # Reset the ESN obtained from website/generated
        G.LOCAL_DB.set_value('esn', '', TABLE_SESSION)
        # Reset the custom ESN (manual ESN from settings)
        G.settings_monitor_suspend(at_first_change=True)
        G.ADDON.setSetting('esn', '')
        # Reset the custom ESN (backup of manual ESN from settings, used in settings_monitor.py)
        G.LOCAL_DB.set_value('custom_esn', '', TABLE_SETTINGS_MONITOR)
        # Perform a new login to get/generate a new ESN
        api.login(ask_credentials=False)
        # Warning after login netflix switch to the main profile! so return to the main screen
        # Open root page
        common.container_update(G.BASE_URL, True)

    @common.inject_video_id(path_offset=1)
    def change_watched_status(self, videoid):
        """Change the watched status locally"""
        # Todo: how get resumetime/playcount of selected item for calculate current watched status?

        profile_guid = G.LOCAL_DB.get_active_profile_guid()
        current_value = G.SHARED_DB.get_watched_status(profile_guid, videoid.value, None, bool)
        if current_value:
            txt_index = 1
            G.SHARED_DB.set_watched_status(profile_guid, videoid.value, False)
        elif current_value is not None and not current_value:
            txt_index = 2
            G.SHARED_DB.delete_watched_status(profile_guid, videoid.value)
        else:
            txt_index = 0
            G.SHARED_DB.set_watched_status(profile_guid, videoid.value, True)
        ui.show_notification(common.get_local_string(30237).split('|')[txt_index])
        common.container_refresh()

    def configuration_wizard(self, pathitems=None):  # pylint: disable=unused-argument
        """Run the add-on configuration wizard"""
        from resources.lib.config_wizard import run_addon_configuration
        run_addon_configuration(show_end_msg=True)

    @common.inject_video_id(path_offset=1)
    def remove_watched_status(self, videoid):
        """Remove the watched status from the Netflix service"""
        if not ui.ask_for_confirmation(common.get_local_string(30168),
                                       common.get_local_string(30300).format(xbmc.getInfoLabel('ListItem.Label'))):
            return
        if not api.remove_watched_status(videoid):
            ui.show_notification('The operation was cancelled due to an unexpected error')
            return
        # Check if item is in the cache
        videoid_exists, list_id = common.make_http_call('get_continuewatching_videoid_exists',
                                                        {'video_id': str(videoid.value)})
        if videoid_exists:
            # Try to remove the videoid from the list in the cache
            try:
                video_list_sorted_data = G.CACHE.get(cache_utils.CACHE_COMMON, list_id)
                del video_list_sorted_data.videos[videoid.value]
                G.CACHE.add(cache_utils.CACHE_COMMON, list_id, video_list_sorted_data)
                common.json_rpc('Input.Down')  # Avoids selection back to the top
            except CacheMiss:
                pass
        common.container_refresh()


def _sync_library(videoid, operation):
    if operation and G.ADDON.getSettingBool('lib_sync_mylist') and G.ADDON.getSettingInt('lib_auto_upd_mode') == 2:
        sync_mylist_profile_guid = G.SHARED_DB.get_value('sync_mylist_profile_guid',
                                                         G.LOCAL_DB.get_guid_owner_profile())
        # Allow to sync library with My List only by chosen profile
        if sync_mylist_profile_guid != G.LOCAL_DB.get_active_profile_guid():
            return
        common.debug('Syncing library due to change of My list')
        if operation == 'add':
            get_library_cls().export_to_library(videoid, False)
        elif operation == 'remove':
            get_library_cls().remove_from_library(videoid, False)
