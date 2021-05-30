# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2020 Stefano Gottardo (original implementation module)
    XML based dialog

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import xbmc
import xbmcgui
import xbmcvfs

from resources.lib import common
from resources.lib.common import IPC_ENDPOINT_MSL
from resources.lib.database.db_utils import TABLE_SESSION
from resources.lib.globals import G
from resources.lib.kodi import ui
from resources.lib.utils.esn import (generate_android_esn, WidevineForceSecLev, get_esn, set_esn, set_website_esn,
                                     get_website_esn)
from resources.lib.utils.logging import LOG

ACTION_PREVIOUS_MENU = 10
ACTION_PLAYER_STOP = 13
ACTION_NAV_BACK = 92


# pylint: disable=invalid-name,no-member
class ESNWidevine(xbmcgui.WindowXMLDialog):
    """Dialog for ESN and Widevine settings"""

    WV_SECLEV_MAP_BTN = {  # Map sec. Lev. type to button id
        WidevineForceSecLev.DISABLED: 40000,
        WidevineForceSecLev.L3: 40001,
        WidevineForceSecLev.L3_4445: 40002
    }

    def __init__(self, *args, **kwargs):  # pylint: disable=unused-argument
        self.changes_applied = False
        self.esn = get_esn()
        self.esn_new = None
        self.wv_force_sec_lev = G.LOCAL_DB.get_value('widevine_force_seclev',
                                                     WidevineForceSecLev.DISABLED,
                                                     table=TABLE_SESSION)
        self.wv_sec_lev_new = None
        self.is_android = common.get_system_platform() == 'android'
        self.action_exit_keys_id = [ACTION_PREVIOUS_MENU,
                                    ACTION_PLAYER_STOP,
                                    ACTION_NAV_BACK]
        super().__init__(*args)

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

    def onClick(self, controlId):
        # [Widevine sec. lev.] radio buttons - this setting can affect the ESN so make a preview of the change
        if controlId in self.WV_SECLEV_MAP_BTN.values():
            self._ensure_wv_btn_check(controlId)
            self.wv_sec_lev_new = list(
                self.WV_SECLEV_MAP_BTN.keys())[list(self.WV_SECLEV_MAP_BTN.values()).index(controlId)]
            self._refresh_esn()
            self._update_esn_label()
        # [Change ESN] button
        if controlId == 30010:
            self._change_esn()
        # [Reset] button - reset all settings to default
        if controlId == 30011:
            self._reset()
        # [Apply changes] button
        if controlId == 40020:
            self._apply_changes()
        # [OK] button - close and keep changes
        if controlId == 40021:
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
        if controlId in [40099, 40022]:
            self._revert_changes()
            self.close()
        # [Save system info] button
        if controlId == 30012:
            _save_system_info()

    def onAction(self, action):
        if action.getId() in self.action_exit_keys_id:
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
                common.make_call('perform_key_handshake', endpoint=IPC_ENDPOINT_MSL)
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
    path = ui.show_browse_dialog(f'{common.get_local_string(30603)} - {filename}')
    if not path:
        return
    # This collect the main data to allow verification checks for problems
    data = f'Netflix add-on version: {G.VERSION}'
    data += f'\nDebug enabled: {LOG.is_enabled}'
    data += f'\nSystem platform: {common.get_system_platform()}'
    data += f'\nMachine architecture: {common.get_machine()}'
    data += f'\nUser agent string: {common.get_user_agent()}'
    data += '\n\n#### Widevine info ####\n'
    if common.get_system_platform() == 'android':
        data += f'\nSystem ID: {G.LOCAL_DB.get_value("drm_system_id", "--not obtained--", TABLE_SESSION)}'
        data += f'\nSecurity level: {G.LOCAL_DB.get_value("drm_security_level", "--not obtained--", TABLE_SESSION)}'
        data += f'\nHDCP level: {G.LOCAL_DB.get_value("drm_hdcp_level", "--not obtained--", TABLE_SESSION)}'
        wv_force_sec_lev = G.LOCAL_DB.get_value('widevine_force_seclev', WidevineForceSecLev.DISABLED,
                                                TABLE_SESSION)
        data += f'\nForced security level setting is: {wv_force_sec_lev}'
    else:
        try:
            from ctypes import (CDLL, c_char_p)
            cdm_lib_file_path = _get_cdm_file_path()
            try:
                lib = CDLL(cdm_lib_file_path)
                data += '\nLibrary status: Correctly loaded'
                try:
                    lib.GetCdmVersion.restype = c_char_p
                    data += f'\nVersion: {lib.GetCdmVersion().decode("utf-8")}'
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
                data += f'\n>>> Error details: {exc}'
        except Exception as exc:  # pylint: disable=broad-except
            data += f'\nThe data could not be obtained. Error details: {exc}'
    data += '\n\n#### ESN ####\n'
    esn = get_esn() or '--not obtained--'
    data += f'\nUsed ESN: {common.censure(esn) if len(esn) > 50 else esn}'
    data += f'\nWebsite ESN: {get_website_esn() or "--not obtained--"}'
    data += f'\nAndroid generated ESN: {(generate_android_esn() or "--not obtained--")}'
    if common.get_system_platform() == 'android':
        data += '\n\n#### Device system info ####\n'
        try:
            import subprocess
            info = subprocess.check_output(['/system/bin/getprop']).decode('utf-8')
            data += f'\n{info}'
        except Exception as exc:  # pylint: disable=broad-except
            data += f'\nThe data could not be obtained. Error: {exc}'
    data += '\n'
    try:
        common.save_file(common.join_folders_paths(path, filename), data.encode('utf-8'))
        ui.show_notification(f'{xbmc.getLocalizedString(35259)}: {filename}')  # 35259=Saved
    except Exception as exc:  # pylint: disable=broad-except
        LOG.error('save_file error: {}', exc)
        ui.show_notification('Error! Try another path')


def _get_cdm_file_path():
    if common.get_system_platform() == 'linux':
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
        raise Exception(f'The CDM path {cdm_path} not exists')
    return common.join_folders_paths(cdm_path, lib_filename)
