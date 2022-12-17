# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2020 Stefano Gottardo - @CastagnaIT (original implementation module)
    ESN Generator

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import re
import time

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


def regen_esn(esn):
    # From the beginning of December 2022 if you are using an ESN for more than about 20 hours
    # Netflix limits the resolution to 540p. The reasons behind this are unknown, there are no changes on website
    # or Android apps. Moreover, if you set the full-length ESN of android app on the add-on, also the original app
    # will be downgraded to 540p without any kind of message.
    if not G.ADDON.getSettingBool('esn_auto_generate'):
        return esn
    from resources.lib.common.device_utils import get_system_platform
    ts_now = int(time.time())
    ts_esn = G.LOCAL_DB.get_value('esn_timestamp', default_value=0)
    # When an ESN has been used for more than 20 hours ago, generate a new ESN
    if ts_esn == 0 or ts_now - ts_esn > 72000:
        if get_system_platform() == 'android':
            if esn[-1] == '-':
                # We have a partial ESN without last 64 chars, so generate and add the 64 chars
                esn += _create_id64chars()
            elif re.search(r'-[0-9]+-[A-Z0-9]{64}', esn):
                # Replace last 64 chars with the new generated one
                esn = esn[:-64] + _create_id64chars()
            else:
                LOG.warn('ESN format not recognized, will be reset with a new ESN')
                esn = generate_android_esn()
        else:
            esn = generate_esn(esn[:-30])
        G.LOCAL_DB.set_value('esn', esn, table=TABLE_SESSION)
        G.LOCAL_DB.set_value('esn_timestamp', ts_now)
        LOG.debug('The ESN has been regenerated (540p workaround).')
    return esn


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
                esn = re.sub(r'[^A-Za-z0-9=-]', '=', esn)
                esn += '-' + system_id + '-' + _create_id64chars()
                LOG.debug('Generated Android ESN: {} (force widevine is set as "{}")', esn, force_widevine)
                return esn
        except OSError:
            pass
    return None


def generate_esn(init_part=None):
    """
    Generate a random ESN
    :param init_part: Specify the initial part to be used e.g. "NFCDCH-02-",
                      if not set will be obtained from the last retrieved from the website
    :return: The generated ESN
    """
    # The initial part of the ESN e.g. "NFCDCH-02-" depends on the web browser used and then the user agent,
    # refer to website to know all types available.
    if not init_part:
        raise Exception('Cannot generate ESN due to missing initial ESN part')
    esn = init_part
    possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    from random import choice
    for _ in range(0, 30):
        esn += choice(possible)
    return esn


def _create_id64chars():
    # The Android full length ESN include to the end a hashed ID of 64 chars,
    # this value is created from the android app by using the Widevine "deviceUniqueId" property value
    # hashed in various ways, not knowing the correct formula, we create a random value.
    # Starting from 12/2022 this value is mandatory to obtain HD resolutions
    from os import urandom
    return re.sub(r'[^A-Za-z0-9=-]', '=', urandom(32).encode('hex').upper())
