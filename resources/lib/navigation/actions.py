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

from resources.lib.globals import g
import resources.lib.common as common
import resources.lib.api.shakti as api
import resources.lib.kodi.ui as ui

from resources.lib.api.exceptions import (MissingCredentialsError, WebsiteParsingError)


class AddonActionExecutor(object):
    """Executes actions"""
    # pylint: disable=no-self-use
    def __init__(self, params):
        common.debug('Initializing AddonActionExecutor: {}', params)
        self.params = params

    def logout(self, pathitems=None):  # pylint: disable=unused-argument
        """Perform account logout"""
        api.logout()

    def save_autologin(self, pathitems):
        """Save autologin data"""
        try:
            g.settings_monitor_suspend(True)
            g.ADDON.setSetting('autologin_user', self.params['autologin_user'])
            g.ADDON.setSetting('autologin_id', pathitems[1])
            g.ADDON.setSetting('autologin_enable', 'true')
            g.settings_monitor_suspend(False)
        except (KeyError, IndexError):
            common.error('Cannot save autologin - invalid params')
        g.CACHE.invalidate()
        common.refresh_container()

    def parental_control(self, pathitems=None):  # pylint: disable=unused-argument
        """Open parental control settings dialog"""
        password = ui.ask_for_password()
        if not password:
            return
        try:
            parental_control_data = api.get_parental_control_data(password)
            ui.show_modal_dialog(ui.xmldialogs.ParentalControl,
                                 'plugin-video-netflix-ParentalControl.xml',
                                 g.ADDON.getAddonInfo('path'),
                                 **parental_control_data)
        except MissingCredentialsError:
            ui.show_ok_dialog('Netflix', common.get_local_string(30009))
        except WebsiteParsingError as exc:
            ui.show_addon_error_info(exc)

    @common.inject_video_id(path_offset=1)
    @common.time_execution(immediate=False)
    def rate_thumb(self, videoid):
        """Rate an item on Netflix. Ask for a thumb rating"""
        # Get updated user rating info for this videoid
        from resources.lib.api.paths import VIDEO_LIST_RATING_THUMB_PATHS
        video_list = api.custom_video_list([videoid.value], VIDEO_LIST_RATING_THUMB_PATHS)
        if video_list.videos:
            videoid_value, video_data = list(video_list.videos.items())[0]  # pylint: disable=unused-variable
            title = video_data.get('title')
            track_id_jaw = video_data.get('trackIds', {})['trackId_jaw']
            is_thumb_rating = video_data.get('userRating', {}).get('type', '') == 'thumb'
            user_rating = video_data.get('userRating', {}).get('userRating') \
                if is_thumb_rating else None
            ui.show_modal_dialog(ui.xmldialogs.RatingThumb,
                                 'plugin-video-netflix-RatingThumb.xml',
                                 g.ADDON.getAddonInfo('path'),
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
        api.update_my_list(videoid, operation)
        _sync_library(videoid, operation)
        common.refresh_container()

    @common.inject_video_id(path_offset=1)
    @common.time_execution(immediate=False)
    def trailer(self, videoid):
        """Get the trailer list"""
        video_list = api.supplemental_video_list(videoid, 'trailers')
        if video_list.videos:
            url = common.build_url(['supplemental', videoid.value, videoid.mediatype, 'trailers'],
                                   mode=g.MODE_DIRECTORY)
            xbmc.executebuiltin('Container.Update({})'.format(url))
        else:
            ui.show_notification(common.get_local_string(30111))

    @common.time_execution(immediate=False)
    def purge_cache(self, pathitems=None):  # pylint: disable=unused-argument
        """Clear the cache. If on_disk param is supplied, also clear cached
        items from disk"""
        g.CACHE.invalidate(self.params.get('on_disk', False))
        if self.params.get('on_disk', False):
            common.delete_file('resources.lib.services.playback.stream_continuity.ndb')
        if not self.params.get('no_notification', False):
            ui.show_notification(common.get_local_string(30135))

    def force_update_mylist(self, pathitems=None):  # pylint: disable=unused-argument
        """Clear the cache of my list to force the update"""
        from resources.lib.cache import CACHE_COMMON
        g.CACHE.invalidate_entry(CACHE_COMMON, 'mylist')
        g.CACHE.invalidate_entry(CACHE_COMMON, 'my_list_items')

    def view_esn(self, pathitems=None):  # pylint: disable=unused-argument
        """Show the ESN in use"""
        ui.show_ok_dialog(common.get_local_string(30016), g.get_esn())

    def reset_esn(self, pathitems=None):  # pylint: disable=unused-argument
        """Reset the ESN stored (retrieved from website and manual)"""
        from resources.lib.database.db_utils import (TABLE_SESSION, TABLE_SETTINGS_MONITOR)
        if not ui.ask_for_confirmation(common.get_local_string(30217),
                                       common.get_local_string(30218)):
            return
        # Reset the ESN obtained from website/generated
        g.LOCAL_DB.set_value('esn', '', TABLE_SESSION)
        # Reset the custom ESN (manual ESN from settings)
        g.settings_monitor_suspend(at_first_change=True)
        g.ADDON.setSetting('esn', '')
        # Reset the custom ESN (backup of manual ESN from settings, used in settings_monitor.py)
        g.LOCAL_DB.set_value('custom_esn', '', TABLE_SETTINGS_MONITOR)
        # Perform a new login to get/generate a new ESN
        api.login(ask_credentials=False)
        # Warning after login netflix switch to the main profile! so return to the main screen
        url = 'plugin://plugin.video.netflix'
        # Open root page
        xbmc.executebuiltin('Container.Update({},replace)'.format(url))  # replace=reset history


def _sync_library(videoid, operation):
    operation = {
        'add': 'export_silent',
        'remove': 'remove_silent'}.get(operation)
    if operation and g.ADDON.getSettingBool('lib_sync_mylist'):
        sync_mylist_profile_guid = g.SHARED_DB.get_value('sync_mylist_profile_guid',
                                                         g.LOCAL_DB.get_guid_owner_profile())
        # Allow to sync library with My List only by chosen profile
        if sync_mylist_profile_guid != g.LOCAL_DB.get_active_profile_guid():
            return
        common.debug('Syncing library due to change of my list')
        # xbmc.executebuiltin is running with Block, to prevent update the list before op. is done
        common.run_plugin(common.build_url([operation], videoid, mode=g.MODE_LIBRARY), block=True)
