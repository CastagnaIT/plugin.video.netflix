# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2020 Stefano Gottardo - @CastagnaIT (original implementation module)
    ESN Generator

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

from re import sub

from resources.lib.database.db_utils import TABLE_SESSION
from resources.lib.globals import G
from resources.lib.common.device_utils import get_system_platform
from resources.lib.common.logging import debug


def generate_android_esn():
    """Generate an ESN if on android or return the one from user_data"""
    if get_system_platform() == 'android':
        import subprocess
        try:
            manufacturer = subprocess.check_output(
                ['/system/bin/getprop',
                 'ro.product.manufacturer']).decode('utf-8').strip(' \t\n\r').upper()
            if manufacturer:
                model = subprocess.check_output(
                    ['/system/bin/getprop',
                     'ro.product.model']).decode('utf-8').strip(' \t\n\r').upper()

                # This product_characteristics check seem no longer used, some L1 devices not have the 'tv' value
                # like Xiaomi Mi Box 3 or SM-T590 devices and is cause of wrong esn generation
                # product_characteristics = subprocess.check_output(
                #     ['/system/bin/getprop',
                #      'ro.build.characteristics']).decode('utf-8').strip(' \t\n\r')
                # Property ro.build.characteristics may also contain more then one value
                # has_product_characteristics_tv = any(
                #     value.strip(' ') == 'tv' for value in product_characteristics.split(','))

                # Netflix Ready Device Platform (NRDP)
                nrdp_modelgroup = subprocess.check_output(
                    ['/system/bin/getprop',
                     'ro.nrdp.modelgroup']).decode('utf-8').strip(' \t\n\r').upper()

                drm_security_level = G.LOCAL_DB.get_value('drm_security_level', '', table=TABLE_SESSION)
                system_id = G.LOCAL_DB.get_value('drm_system_id', table=TABLE_SESSION)

                # Some device with false Widevine certification can be specified as Widevine L1
                # but we do not know how NF original app force the fallback to L3, so we add a manual setting
                is_l3_forced = bool(G.ADDON.getSettingBool('force_widevine_l3'))
                if is_l3_forced:
                    drm_security_level = 'L3'
                    # We do not know if override the DRM System ID to 4445 is a good behaviour for all devices,
                    # but at least for Beelink GT-King (S922X) this is needed
                    system_id = '4445'

                # The original android ESN generator is not full replicable
                # because we can not access easily to android APIs to get system data
                # First NF identifies the device in this way and in the following order:
                # 1) if getPackageManager().hasSystemFeature("org.chromium.arc") == true
                #                 the device is : DEV_TYPE_CHROME_OS (Chrome OS)
                # 2) if getSystemService(Context.DISPLAY_SERVICE)).getDisplay(0) == null
                #                 the device is : DEV_TYPE_ANDROID_STB (Set-Top Box)
                # 3) if getSystemService(Context.UI_MODE_SERVICE)).getCurrentModeType() == UI_MODE_TYPE_TELEVISION
                #                 the device is : DEV_TYPE_ANDROID_TV
                # 4) if 528 is <= of (calculated resolution display):
                #    DisplayMetrics dMetr = new DisplayMetrics();
                #    defaultDisplay.getRealMetrics(displayMetrics);
                #    float disDens = displayMetrics.density;
                #    if 528 <= Math.min((dMetr.widthPixels / disDens, (dMetr.heightPixels / disDens)
                #                 the device is : DEV_TYPE_TABLET
                # 5) if all other cases are not suitable, then the device is :  DEV_TYPE_PHONE

                # Then after identifying the device type, a specific letter will be added after the prefix "PRV-":
                #   DEV_TYPE_CHROME_OS      "PRV-C"
                #   DEV_TYPE_ANDROID_STB    "PRV-B"
                #   DEV_TYPE_ANDROID_TV     "PRV-" (no letter specified)
                #   DEV_TYPE_TABLET         "PRV-T"
                #   DEV_TYPE_PHONE          "PRV-P"

                # if has_product_characteristics_tv and \
                #         G.LOCAL_DB.get_value('drm_security_level', '', table=TABLE_SESSION) == 'L1':
                if drm_security_level == 'L1':
                    esn = 'NFANDROID2-PRV-'
                    if nrdp_modelgroup:
                        esn += nrdp_modelgroup + '-'
                    else:
                        esn += model.replace(' ', '') + '-'
                else:
                    esn = 'NFANDROID1-PRV-'
                    esn += 'T-L3-'

                esn += '{:=<5.5}'.format(manufacturer)
                esn += model[:45].replace(' ', '=')
                esn = sub(r'[^A-Za-z0-9=-]', '=', esn)
                if system_id:
                    esn += '-' + system_id + '-'
                debug('Generated Android ESN: {} is L3 forced: {}', esn, is_l3_forced)
                return esn
        except OSError:
            pass
    return None


def generate_esn(prefix=''):
    """Generate a random ESN"""
    # For possibles prefixes see website, are based on browser user agent
    import random
    esn = prefix
    possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    for _ in range(0, 30):
        esn += random.choice(possible)
    debug('Generated random ESN: {}', esn)
    return esn
