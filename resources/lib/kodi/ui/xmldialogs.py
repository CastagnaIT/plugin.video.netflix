# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    XML based dialogs

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
# pylint: disable=invalid-name,missing-docstring,attribute-defined-outside-init
import time

import xbmc
import xbmcgui
import xbmcvfs

from resources.lib import common
from resources.lib.common import run_threaded, get_machine, make_call
from resources.lib.database.db_utils import TABLE_SESSION
from resources.lib.globals import G
from resources.lib.kodi import ui
from resources.lib.utils.esn import (generate_android_esn, WidevineForceSecLev, get_esn, set_esn, set_website_esn,
                                     get_website_esn)
from resources.lib.utils.logging import LOG

ACTION_PREVIOUS_MENU = 10
ACTION_PLAYER_STOP = 13
ACTION_NAV_BACK = 92
ACTION_NOOP = 999

XBFONT_LEFT = 0x00000000
XBFONT_RIGHT = 0x00000001
XBFONT_CENTER_X = 0x00000002
XBFONT_CENTER_Y = 0x00000004
XBFONT_TRUNCATED = 0x00000008
XBFONT_JUSTIFY = 0x00000010

CMD_CLOSE_DIALOG_BY_NOOP = 'AlarmClock(closedialog,Action(noop),{},silent)'


# @time_execution(immediate=True)
def show_modal_dialog(non_blocking, dlg_class, xml, path, **kwargs):
    """
    Show a modal Dialog in the UI.
    Pass kwargs minutes and/or seconds to have the dialog automatically
    close after the specified time.

    :return if exists return self.return_value value of dlg_class (if non_blocking=True return always None)
    """
    # WARNING: doModal when invoked does not release the function immediately!
    # it seems that doModal waiting for all window operations to be completed before return,
    # for example the "Skip" dialog takes about 30 seconds to release the function (test on Kodi 19.x)
    # To be taken into account because it can do very big delays in the execution of the invoking code
    return run_threaded(non_blocking, _show_modal_dialog, dlg_class, xml, path, **kwargs)


def _show_modal_dialog(dlg_class, xml, path, **kwargs):
    dlg = dlg_class(xml, path, 'default', '1080i', **kwargs)
    minutes = kwargs.get('minutes', 0)
    seconds = kwargs.get('seconds', 0)
    if minutes > 0 or seconds > 0:
        # Bug in Kodi AlarmClock function, if only the seconds are passed
        # the time conversion inside the function multiply the seconds by 60
        if seconds > 59 and minutes == 0:
            alarm_time = time.strftime('%M:%S', time.gmtime(seconds))
        else:
            alarm_time = '{:02d}:{:02d}'.format(minutes, seconds)
        xbmc.executebuiltin(CMD_CLOSE_DIALOG_BY_NOOP.format(alarm_time))
    dlg.doModal()
    if hasattr(dlg, 'return_value'):
        return dlg.return_value
    return None


class Skip(xbmcgui.WindowXMLDialog):
    """
    Dialog for skipping video parts (intro, recap, ...)
    """
    def __init__(self, *args, **kwargs):
        self.skip_to = kwargs['skip_to']
        self.label = kwargs['label']

        self.action_exitkeys_id = [ACTION_PREVIOUS_MENU,
                                   ACTION_PLAYER_STOP,
                                   ACTION_NAV_BACK,
                                   ACTION_NOOP]

        if get_machine()[0:5] == 'armv7':
            super().__init__()
        else:
            try:
                super().__init__(*args, **kwargs)
                #xbmcgui.WindowXMLDialog.__init__(self, *args, **kwargs)
            except Exception:  # pylint: disable=broad-except
                super().__init__()

    def onInit(self):
        self.getControl(6012).setLabel(self.label)

    def onClick(self, controlID):
        if controlID == 6012:
            xbmc.Player().seekTime(self.skip_to)
            self.close()

    def onAction(self, action):
        if action.getId() in self.action_exitkeys_id:
            self.close()


# pylint: disable=no-member
class ParentalControl(xbmcgui.WindowXMLDialog):
    """
    Dialog for parental control settings
    """
    def __init__(self, *args, **kwargs):
        # Keep pin option, there is still some reference in the netflix code
        # self.current_pin = kwargs.get('pin')
        self.data = kwargs['data']
        self.rating_levels = kwargs['rating_levels']
        self.current_maturity = self.data['maturity']
        self.current_level_index = kwargs['current_level_index']
        self.profile_info = self.data['profileInfo']
        self.levels_count = len(self.rating_levels)
        self.status_base_desc = G.ADDON.getLocalizedString(30233)
        self.action_exitkeys_id = [ACTION_PREVIOUS_MENU,
                                   ACTION_PLAYER_STOP,
                                   ACTION_NAV_BACK]
        if get_machine()[0:5] == 'armv7':
            #xbmcgui.WindowXMLDialog.__init__(self)
            super().__init__()
        else:
            try:
                super().__init__(*args, **kwargs)
                #xbmcgui.WindowXMLDialog.__init__(self, *args, **kwargs)
            except Exception:  # pylint: disable=broad-except
                super().__init__()

    def onInit(self):
        self._generate_levels_labels()
        # Set maturity level status description
        self._update_status_desc(self.current_level_index)
        # Set profile name to label description
        self.getControl(10003).setLabel(G.ADDON.getLocalizedString(30232).format(self.profile_info['profileName']))
        # PIN input
        # edit_control = self.getControl(10002)
        # edit_control.setType(xbmcgui.INPUT_TYPE_NUMBER, G.ADDON.getLocalizedString(30002))
        # edit_control.setText(self.current_pin)
        # Maturity level slider
        slider_control = self.getControl(10004)
        # setInt(value, min, delta, max)
        slider_control.setInt(self.current_level_index, 0, 1, self.levels_count - 1)

    def onClick(self, controlID):
        if controlID == 10028:  # Save and close dialog
            # pin = self.getControl(10002).getText()
            # # Validate pin length
            # if not self._validate_pin(pin):
            #     return
            import resources.lib.utils.api_requests as api
            data = {'guid': self.data['profileInfo']['guid'],
                    'experience': self.data['experience'],
                    'maturity': self.rating_levels[self.current_level_index]['value'],
                    'token': self.data['token']}
            # Send changes to the service
            api.set_parental_control_data(data)

            # The selection of the maturity level affects the lists data as a filter,
            # so you need to clear the lists in the cache in order not to create inconsistencies
            from resources.lib.common.cache_utils import CACHE_COMMON, CACHE_GENRES, CACHE_MYLIST, CACHE_SEARCH
            G.CACHE.clear([CACHE_COMMON, CACHE_GENRES, CACHE_MYLIST, CACHE_SEARCH])
            self.close()
        if controlID in [10029, 100]:  # Close dialog
            self.close()

    def onAction(self, action):
        if action.getId() in self.action_exitkeys_id:
            self.close()
            return
        # Bad thing to check for changes in this way, but i have not found any other ways
        slider_value = self.getControl(10004).getInt()
        if slider_value != self.current_level_index:
            self._update_status_desc(slider_value)

    def _update_status_desc(self, new_level_index=None):
        self.current_level_index = self.getControl(10004).getInt() if new_level_index is None else new_level_index
        # Update labels color of slider steps
        for index in range(0, self.levels_count):
            maturity_name = '[' + self.rating_levels[index]['label'] + ']'
            ml_label = '[COLOR red]{}[/COLOR]'.format(maturity_name) if index <= self.current_level_index else maturity_name
            self.controls[index].setLabel(ml_label)
        # Update status description
        hint = self.rating_levels[self.current_level_index]['description']
        ml_labels_included = [self.rating_levels[index]['label'] for index in range(0, self.current_level_index + 1)]
        status_desc = self.status_base_desc.format(', '.join(ml_labels_included)) + '[CR]' + hint
        self.getControl(10009).setLabel(status_desc)

    # def _validate_pin(self, pin_value):
    #     if len(pin_value or '') != 4:
    #         show_ok_dialog('PIN', G.ADDON.getLocalizedString(30106))
    #         return False
    #     return True

    def _generate_levels_labels(self):
        """Generate descriptions for the levels dynamically"""
        # Limit to 1200 px max (should be longer than slider)
        width = int(1200 / self.levels_count)
        height = 100
        pos_x = 175
        pos_y = 508  # 668
        self.controls = {}
        for index, rating_level in enumerate(self.rating_levels):
            current_x = pos_x + (width * index)
            maturity_name = '[' + rating_level['label'] + ']'
            lbl = xbmcgui.ControlLabel(current_x, pos_y, width, height, maturity_name,
                                       font='font10',
                                       alignment=XBFONT_CENTER_X)
            self.controls.update({index: lbl})
            self.addControl(lbl)


# pylint: disable=no-member
class RatingThumb(xbmcgui.WindowXMLDialog):
    """
    Dialog for rating a tvshow or movie
    """
    def __init__(self, *args, **kwargs):
        self.videoid = kwargs['videoid']
        self.track_id_jaw = kwargs['track_id_jaw']
        self.title = kwargs.get('title', '--')
        self.user_rating = kwargs.get('user_rating', 0)
        # Netflix user rating thumb values
        # 0 = No rated
        # 1 = thumb down
        # 2 = thumb up
        self.action_exitkeys_id = [ACTION_PREVIOUS_MENU,
                                   ACTION_PLAYER_STOP,
                                   ACTION_NAV_BACK]
        if get_machine()[0:5] == 'armv7':
            super().__init__()
        else:
            try:
                super().__init__(*args, **kwargs)
            except Exception:  # pylint: disable=broad-except
                super().__init__()

    def onInit(self):
        self.getControl(10000).setLabel(self.title)
        # Kodi does not allow to change button textures in runtime
        # and you can not add nested controls via code,
        # so the only alternative is to create double XML buttons
        # and eliminate those that are not needed
        focus_id = 10010
        if self.user_rating == 0:  # No rated
            self.removeControl(self.getControl(10012))
            self.removeControl(self.getControl(10022))
        if self.user_rating == 1:  # Thumb down set
            self.removeControl(self.getControl(10012))
            self.removeControl(self.getControl(10020))
            self.getControl(10010).controlRight(self.getControl(10022))
            self.getControl(10040).controlLeft(self.getControl(10022))
        if self.user_rating == 2:  # Thumb up set
            focus_id = 10012
            self.removeControl(self.getControl(10010))
            self.removeControl(self.getControl(10022))
            self.getControl(10020).controlLeft(self.getControl(10012))
        self.setFocusId(focus_id)

    def onClick(self, controlID):
        if controlID in [10010, 10020, 10012, 10022]:  # Rating and close
            rating_map = {10010: 2, 10020: 1, 10012: 0, 10022: 0}
            rating_value = rating_map[controlID]
            from resources.lib.utils.api_requests import rate_thumb
            rate_thumb(self.videoid, rating_value, self.track_id_jaw)
            self.close()
        if controlID in [10040, 100]:  # Close
            self.close()

    def onAction(self, action):
        if action.getId() in self.action_exitkeys_id:
            self.close()


def show_profiles_dialog(title=None, title_prefix=None, preselect_guid=None):
    """
    Show a dialog to select a profile

    :return guid of selected profile or None
    """
    if not title:
        title = G.ADDON.getLocalizedString(30128)
    if title_prefix:
        title = title_prefix + ' - ' + title
    # Get profiles data
    # pylint: disable=unused-variable
    list_data, extra_data = make_call('get_profiles',
                                      {'request_update': True,
                                       'preselect_guid': preselect_guid,
                                       'detailed_info': False})
    return show_modal_dialog(False,
                             Profiles,
                             'plugin-video-netflix-Profiles.xml',
                             G.ADDON.getAddonInfo('path'),
                             title=title,
                             list_data=list_data,
                             preselect_guid=preselect_guid)


# pylint: disable=no-member
class Profiles(xbmcgui.WindowXMLDialog):
    """
    Dialog for profile selection
    """
    def __init__(self, *args, **kwargs):
        self.ctrl_list = None
        self.return_value = None
        self.title = kwargs['title']
        self.list_data = kwargs['list_data']
        self.preselect_guid = kwargs.get('preselect_guid')
        self.action_exitkeys_id = [ACTION_PREVIOUS_MENU,
                                   ACTION_PLAYER_STOP,
                                   ACTION_NAV_BACK]
        if get_machine()[0:5] == 'armv7':
            super().__init__()
        else:
            try:
                super().__init__(*args, **kwargs)
            except Exception:  # pylint: disable=broad-except
                super().__init__()

    def onInit(self):
        self.getControl(99).setLabel(self.title)
        self.ctrl_list = self.getControl(10001)
        from resources.lib.navigation.directory_utils import convert_list_to_list_items
        self.ctrl_list.addItems(convert_list_to_list_items(self.list_data))
        # Preselect the ListItem by guid
        self.ctrl_list.selectItem(0)
        if self.preselect_guid:
            for index, profile_data in enumerate(self.list_data):
                if profile_data['properties']['nf_guid'] == self.preselect_guid:
                    self.ctrl_list.selectItem(index)
                    break
        self.setFocusId(10001)

    def onClick(self, controlID):
        if controlID == 10001:  # Save and close dialog
            sel_list_item = self.ctrl_list.getSelectedItem()
            # 'nf_guid' property is set to Listitems from _create_profile_item of dir_builder_items.py
            self.return_value = sel_list_item.getProperty('nf_guid')
            self.close()
        if controlID in [10029, 100]:  # Close
            self.close()

    def onAction(self, action):
        if action.getId() in self.action_exitkeys_id:
            self.close()


def show_esn_widevine_dialog():
    """Show a dialog for ESN and Widevine settings"""
    return show_modal_dialog(False,
                             ESNWidevine,
                             'plugin-video-netflix-ESN-Widevine.xml',
                             G.ADDON.getAddonInfo('path'))


# pylint: disable=no-member
class ESNWidevine(xbmcgui.WindowXMLDialog):
    """Dialog for ESN and Widevine settings"""
    WV_SECLEV_MAP_BTN = {  # Map sec. Lev. type to button id
        WidevineForceSecLev.DISABLED: 40000,
        WidevineForceSecLev.L3: 40001,
        WidevineForceSecLev.L3_4445: 40002
    }

    def __init__(self, *args, **kwargs):
        self.changes_applied = False
        self.esn = get_esn()
        self.esn_new = None
        self.wv_force_sec_lev = G.LOCAL_DB.get_value('widevine_force_seclev',
                                                     WidevineForceSecLev.DISABLED,
                                                     table=TABLE_SESSION)
        self.wv_sec_lev_new = None
        self.is_android = common.get_system_platform() == 'android'
        self.action_exitkeys_id = [ACTION_PREVIOUS_MENU,
                                   ACTION_PLAYER_STOP,
                                   ACTION_NAV_BACK]
        if get_machine()[0:5] == 'armv7':
            super().__init__()
        else:
            try:
                super().__init__(*args, **kwargs)
            except Exception:  # pylint: disable=broad-except
                super().__init__()

    def onInit(self):
        # Set label to Widevine sec. lev. radio buttons
        self.getControl(40001).setLabel(common.get_local_string(30605).format(WidevineForceSecLev.L3))
        self.getControl(40002).setLabel(common.get_local_string(30605).format(WidevineForceSecLev.L3_4445))
        # Set the current ESN to Label
        self.getControl(30000).setLabel(self.esn)
        # Set the current Widevine security level to the radio buttons
        self.getControl(self.WV_SECLEV_MAP_BTN[self.wv_force_sec_lev]).setSelected(True)
        # Hide force L3 on non-android systems (L1 is currently supported only to android)
        if not self.is_android:
            for _sec_lev, _id in self.WV_SECLEV_MAP_BTN.items():
                if _sec_lev != WidevineForceSecLev.DISABLED:
                    self.getControl(_id).setVisible(False)

    def onClick(self, controlID):
        # [Widevine sec. lev.] radio buttons - this setting can affect the ESN so make a preview of the change
        if controlID in self.WV_SECLEV_MAP_BTN.values():
            self._ensure_wv_btn_check(controlID)
            self.wv_sec_lev_new = list(
                self.WV_SECLEV_MAP_BTN.keys())[list(self.WV_SECLEV_MAP_BTN.values()).index(controlID)]
            self._refresh_esn()
            self._update_esn_label()
        # [Change ESN] button
        if controlID == 30010:
            self._change_esn()
        # [Reset] button - reset all settings to default
        if controlID == 30011:
            self._reset()
        # [Apply changes] button
        if controlID == 40020:
            self._apply_changes()
        # [OK] button - close and keep changes
        if controlID == 40021:
            if not self.changes_applied:
                # The changes to MSL (key handshake) will be done when will be played a video
                set_esn(self.esn_new or self.esn)
                G.LOCAL_DB.set_value('widevine_force_seclev',
                                     self.wv_sec_lev_new or self.wv_force_sec_lev,
                                     TABLE_SESSION)
            # Delete manifests cache, to prevent possible problems in relation to previous ESN used
            from resources.lib.common.cache_utils import CACHE_MANIFESTS
            G.CACHE.clear([CACHE_MANIFESTS])
            self.close()
        # [X or Cancel] button - close and cancel changes
        if controlID in [40099, 40022]:
            self._revert_changes()
            self.close()
        # [Save system info] button
        if controlID == 30012:
            _save_system_info()

    def onAction(self, action):
        if action.getId() in self.action_exitkeys_id:
            self._revert_changes()
            self.close()

    def _esn_checks(self):
        """Sanity checks for custom ESN"""
        esn = self.esn_new or self.esn
        if self.is_android:
            if not esn.startswith(('NFANDROID1-PRV-', 'NFANDROID2-PRV-')) or len(esn.split('-')) < 5:
                return False
        else:
            if len(esn.split('-')) != 3 or len(esn) != 40:
                return False
        return True

    def _ensure_wv_btn_check(self, _chosen_id):
        """Ensure that only the chosen Widevine sec. lev. radio button is checked"""
        for _id in self.WV_SECLEV_MAP_BTN.values():
            is_checked = self.getControl(_id).isSelected()
            if _id == _chosen_id:
                if not is_checked:
                    self.getControl(_id).setSelected(True)
            elif is_checked:
                self.getControl(_id).setSelected(False)

    def _refresh_esn(self):
        """Refresh the ESN based on Widevine security level (ANDROID ONLY)"""
        # Refresh only is when there is no a full-length ESN
        if self.is_android and len(self.esn_new or self.esn) < 50:
            self.esn_new = generate_android_esn(wv_force_sec_lev=self.wv_sec_lev_new or self.wv_force_sec_lev)

    def _update_esn_label(self):
        self.getControl(30000).setLabel(self.esn_new or self.esn)

    def _change_esn(self):
        esn_custom = ui.ask_for_input(common.get_local_string(30602), self.esn_new or self.esn)
        if esn_custom:
            if not self._esn_checks():
                # Wrong custom ESN format type
                ui.show_ok_dialog(common.get_local_string(30600), common.get_local_string(30608))
            else:
                self.esn_new = esn_custom
            self._update_esn_label()

    def _reset(self):
        if not ui.ask_for_confirmation(common.get_local_string(13007),  # 13007=Reset
                                       common.get_local_string(30609)):
            return
        with common.show_busy_dialog():
            # Set WV Sec. Lev. to Disabled
            self._ensure_wv_btn_check(self.WV_SECLEV_MAP_BTN[WidevineForceSecLev.DISABLED])
            self.wv_sec_lev_new = WidevineForceSecLev.DISABLED
            if self.is_android:
                # Generate the ESN
                self.esn_new = generate_android_esn(wv_force_sec_lev=self.wv_sec_lev_new)
            else:
                # To retrieve the ESN from the website,
                # to avoid possible problems we refresh the nf session data to get a new ESN
                set_website_esn('')
                common.make_call('refresh_session_data', {'update_profiles': False})
                self.esn_new = get_website_esn()
                if not self.esn_new:
                    raise Exception('It was not possible to obtain the ESN, try restarting the add-on')
        self._update_esn_label()

    def _apply_changes(self):
        with common.show_busy_dialog():
            set_esn(self.esn_new or self.esn)
            G.LOCAL_DB.set_value('widevine_force_seclev', self.wv_sec_lev_new or self.wv_force_sec_lev, TABLE_SESSION)
            # Try apply the changes by performing the MSL key handshake right now
            try:
                common.make_call('perform_key_handshake', port_setting_name='msl_service_port')
                # When the MSL not raise errors not always means that the device can play the videos
                # because the MSL manifest/license request may not be granted (you have to play a video to know it).
                ui.show_ok_dialog(common.get_local_string(30600), common.get_local_string(30606))
            except Exception as exc:  # pylint: disable=broad-except
                ui.show_ok_dialog(common.get_local_string(30600), common.get_local_string(30607).format(exc))
        self.changes_applied = True

    def _revert_changes(self):
        if self.changes_applied:
            # Revert the saved changes
            # The changes to MSL (key handshake) will be done when will be played a video
            set_esn(self.esn)
            G.LOCAL_DB.set_value('widevine_force_seclev', self.wv_force_sec_lev, TABLE_SESSION)
            # Delete manifests cache, to prevent possible problems in relation to previous ESN used
            from resources.lib.common.cache_utils import CACHE_MANIFESTS
            G.CACHE.clear([CACHE_MANIFESTS])


def _save_system_info():
    # Ask to save to a file
    filename = 'NFSystemInfo.txt'
    path = ui.show_browse_dialog(common.get_local_string(30603) + ' - ' + filename)
    if not path:
        return
    # This collect the main data to allow verification checks for problems
    data = 'Netflix add-on version: ' + G.VERSION
    data += '\nDebug logging level: ' + LOG.level
    data += '\nSystem platform: ' + common.get_system_platform()
    data += '\nMachine architecture: ' + common.get_machine()
    data += '\nUser agent string: ' + common.get_user_agent()
    data += '\n\n' + '#### Widevine info ####\n'
    if common.get_system_platform() == 'android':
        data += '\nSystem ID: ' + G.LOCAL_DB.get_value('drm_system_id', '--not obtained--', TABLE_SESSION)
        data += '\nSecurity level: ' + G.LOCAL_DB.get_value('drm_security_level', '--not obtained--', TABLE_SESSION)
        data += '\nHDCP level: ' + G.LOCAL_DB.get_value('drm_hdcp_level', '--not obtained--', TABLE_SESSION)
        wv_force_sec_lev = G.LOCAL_DB.get_value('widevine_force_seclev', WidevineForceSecLev.DISABLED,
                                                TABLE_SESSION)
        data += '\nForced security level setting is: ' + wv_force_sec_lev
    else:
        try:
            from ctypes import (CDLL, c_char_p)
            cdm_lib_file_path = _get_cdm_file_path()
            try:
                lib = CDLL(cdm_lib_file_path)
                data += '\nLibrary status: Correctly loaded'
                try:
                    lib.GetCdmVersion.restype = c_char_p
                    data += '\nVersion: ' + lib.GetCdmVersion().decode('utf-8')
                except Exception:  # pylint: disable=broad-except
                    # This can happen if the endpoint 'GetCdmVersion' is changed
                    data += '\nVersion: Reading error'
            except Exception as exc:  # pylint: disable=broad-except
                # This should not happen but currently InputStream Helper does not perform any verification checks on
                # downloaded and installed files, so if due to an problem it installs a CDM for a different architecture
                # or the files are corrupted, the user can no longer play videos and does not know what to do
                data += '\nLibrary status: Error loading failed'
                data += '\n>>> It is possible that is installed a CDM of a wrong architecture or is corrupted'
                data += '\n>>> Suggested solutions:'
                data += '\n>>> - Restore a previous version of Widevine library from InputStream Helper add-on settings'
                data += '\n>>> - Report the problem to the GitHub of InputStream Helper add-on'
                data += '\n>>> Error details: {}'.format(exc)
        except Exception as exc:  # pylint: disable=broad-except
            data += '\nThe data could not be obtained. Error details: {}'.format(exc)
    data += '\n\n' + '#### ESN ####\n'
    esn = get_esn() or '--not obtained--'
    data += '\nUsed ESN: ' + common.censure(esn) if len(esn) > 50 else esn
    data += '\nWebsite ESN: ' + (get_website_esn() or '--not obtained--')
    data += '\nAndroid generated ESN: ' + (generate_android_esn() or '--not obtained--')
    if common.get_system_platform() == 'android':
        data += '\n\n' + '#### Device system info ####\n'
        try:
            import subprocess
            info = subprocess.check_output(['/system/bin/getprop']).decode('utf-8')
            data += '\n' + info
        except Exception as exc:  # pylint: disable=broad-except
            data += '\nThe data could not be obtained. Error: {}'.format(exc)
    data += '\n'
    try:
        common.save_file(common.join_folders_paths(path, filename), data.encode('utf-8'))
        ui.show_notification('{}: {}'.format(xbmc.getLocalizedString(35259), filename))  # 35259=Saved
    except Exception as exc:  # pylint: disable=broad-except
        LOG.error('save_file error: {}', exc)
        ui.show_notification('Error! Try another path')


def _get_cdm_file_path():
    if common.get_system_platform() in ['linux', 'linux raspberrypi']:
        lib_filename = 'libwidevinecdm.so'
    elif common.get_system_platform() in ['windows', 'uwp']:
        lib_filename = 'widevinecdm.dll'
    elif common.get_system_platform() == 'osx':
        lib_filename = 'libwidevinecdm.dylib'
        # import ctypes.util
        # lib_filename = util.find_library('libwidevinecdm.dylib')
    else:
        lib_filename = None
    if not lib_filename:
        raise Exception('Widevine library filename not mapped for this operative system')
    # Get the CDM path from inputstream.adaptive (such as: ../.kodi/cdm)
    from xbmcaddon import Addon
    addon = Addon('inputstream.adaptive')
    cdm_path = xbmcvfs.translatePath(addon.getSetting('DECRYPTERPATH'))
    if not common.folder_exists(cdm_path):
        raise Exception('The CDM path {} not exists'.format(cdm_path))
    return common.join_folders_paths(cdm_path, lib_filename)
