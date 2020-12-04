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
from .logging import LOG


# 25/11/2020 - Follow Android ESN generator is changed (current method not yet known)
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
# Then after identifying the device type, a specific letter will be added after the prefix "PRV-"

# ESN Device categories (updated 25/11/2020)
#  Unknown or Phone "PRV-P"
#  Tablet?          "PRV-T"   (should be for tablet)
#  Tablet           "PRV-C"   (should be for Chrome OS devices only)
#  Google TV        "PRV-B"   (Set-Top Box)
#  Smart Display    "PRV-E"
#  Android TV       "PRV-"    (without letter specified)


class ForceWidevine:  # pylint: disable=no-init, disable=too-few-public-methods
    """The enum values of 'force_widevine' add-on setting"""
    DISABLED = 'Disabled'
    L3 = 'Widevine L3'
    L3_4445 = 'Widevine L3 (ID-4445)'


def get_esn():
    """Get the generated esn or if set get the custom esn"""
    custom_esn = G.ADDON.getSetting('esn')
    return custom_esn if custom_esn else G.LOCAL_DB.get_value('esn', '', table=TABLE_SESSION)


def generate_android_esn():
    """Generate an ESN if on android or return the one from user_data"""
    from resources.lib.common.device_utils import get_system_platform
    if get_system_platform() == 'android':
        import subprocess
        try:
            sdk_version = int(subprocess.check_output(['/system/bin/getprop', 'ro.build.version.sdk']))
            manufacturer = subprocess.check_output(
                ['/system/bin/getprop',
                 'ro.product.manufacturer']).decode('utf-8').strip(' \t\n\r').upper()
            if manufacturer:
                model = subprocess.check_output(
                    ['/system/bin/getprop',
                     'ro.product.model']).decode('utf-8').strip(' \t\n\r').upper()

                # Netflix Ready Device Platform (NRDP)
                nrdp_modelgroup = subprocess.check_output(
                    ['/system/bin/getprop',
                     'ro.vendor.nrdp.modelgroup' if sdk_version >= 28 else 'ro.nrdp.modelgroup']
                ).decode('utf-8').strip(' \t\n\r').upper()

                drm_security_level = G.LOCAL_DB.get_value('drm_security_level', '', table=TABLE_SESSION)
                system_id = G.LOCAL_DB.get_value('drm_system_id', table=TABLE_SESSION)

                # Some device with false Widevine certification can be specified as Widevine L1
                # but we do not know how NF original app force the fallback to L3, so we add a manual setting
                force_widevine = G.ADDON.getSettingString('force_widevine')
                if force_widevine == ForceWidevine.L3:
                    drm_security_level = 'L3'
                elif force_widevine == ForceWidevine.L3_4445:
                    # For some devices the Netflix android app change the DRM System ID to 4445
                    drm_security_level = 'L3'
                    system_id = '4445'

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
                LOG.debug('Generated Android ESN: {} (force widevine is set as "{}")', esn, force_widevine)
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
    LOG.debug('Generated random ESN: {}', esn)
    return esn
