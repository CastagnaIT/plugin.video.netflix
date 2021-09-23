# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2020 Stefano Gottardo - @CastagnaIT (original implementation module)
    ESN Generator

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
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


class WidevineForceSecLev:  # pylint: disable=no-init, disable=too-few-public-methods
    """The values accepted for 'widevine_force_seclev' TABLE_SESSION setting"""
    DISABLED = 'Disabled'
    L3 = 'L3'
    L3_4445 = 'L3 (ID 4445)'


def get_esn():
    """Get the ESN currently in use"""
    return G.LOCAL_DB.get_value('esn', '', table=TABLE_SESSION)


def set_esn(esn=None):
    """
    Set the ESN to be used
    :param esn: if None the ESN will be generated or retrieved
    :return: The ESN set
    """
    if not esn:
        # Generate the ESN if we are on Android or get it from the website
        esn = generate_android_esn() or get_website_esn()
        if not esn:
            raise Exception('It was not possible to obtain an ESN')
    G.LOCAL_DB.set_value('esn', esn, TABLE_SESSION)
    return esn


def get_website_esn():
    """Get the ESN set by the website"""
    return G.LOCAL_DB.get_value('website_esn', table=TABLE_SESSION)


def set_website_esn(esn):
    """Save the ESN of the website"""
    G.LOCAL_DB.set_value('website_esn', esn, TABLE_SESSION)


def generate_android_esn(wv_force_sec_lev=None):
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
                if not wv_force_sec_lev:
                    wv_force_sec_lev = G.LOCAL_DB.get_value('widevine_force_seclev',
                                                            WidevineForceSecLev.DISABLED,
                                                            table=TABLE_SESSION)
                if wv_force_sec_lev == WidevineForceSecLev.L3:
                    drm_security_level = 'L3'
                elif wv_force_sec_lev == WidevineForceSecLev.L3_4445:
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

                esn += f'{manufacturer:=<5.5}'
                esn += model[:45].replace(' ', '=')
                esn = sub(r'[^A-Za-z0-9=-]', '=', esn)
                if system_id:
                    esn += f'-{system_id}-'
                LOG.debug('Generated Android ESN: {} (widevine force sec.lev. set as "{}")', esn, wv_force_sec_lev)
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
