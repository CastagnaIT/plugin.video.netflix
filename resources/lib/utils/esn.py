# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2020 Stefano Gottardo - @CastagnaIT (original implementation module)
    ESN Generator

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import time
import re

from resources.lib.common.exceptions import ErrorMsg
from resources.lib.database.db_utils import TABLE_SESSION
from resources.lib.globals import G
from .logging import LOG


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
    :param esn: if None the ESN will be generated or retrieved, and updated the ESN timestamp
    :return: The ESN set
    """
    if not esn:
        # Generate the ESN if we are on Android or get it from the website
        esn = generate_android_esn() or get_website_esn()
        if not esn:
            raise ErrorMsg('It was not possible to obtain an ESN')
        G.LOCAL_DB.set_value('esn_timestamp', int(time.time()))
    G.LOCAL_DB.set_value('esn', esn, TABLE_SESSION)
    return esn


def get_website_esn():
    """Get the ESN set by the website"""
    return G.LOCAL_DB.get_value('website_esn', table=TABLE_SESSION)


def set_website_esn(esn):
    """Save the ESN of the website"""
    G.LOCAL_DB.set_value('website_esn', esn, TABLE_SESSION)


def regen_esn(esn):
    """
    Regenerate the ESN on the basis of the existing one,
    to preserve possible user customizations,
    this method will only be executed every 20 hours.
    """
    # From the beginning of December 2022 if you are using an ESN for more than about 20 hours
    # Netflix limits the resolution to 540p. The reasons behind this are unknown, there are no changes on website
    # or Android apps. Moreover, if you set the full-length ESN of android app on the add-on, also the original app
    # will be downgraded to 540p without any kind of message.
    if not G.LOCAL_DB.get_value('esn_auto_generate', True):
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
        set_esn(esn)
        G.LOCAL_DB.set_value('esn_timestamp', ts_now)
        LOG.debug('The ESN has been regenerated (540p workaround).')
    return esn


def generate_android_esn(wv_force_sec_lev=None):
    """Generate an ESN if on android or return the one from user_data"""
    from resources.lib.common.device_utils import get_system_platform, get_android_system_props
    if get_system_platform() == 'android':
        props = get_android_system_props()
        is_android_tv = 'TV' in props.get('ro.build.characteristics', '').upper()
        if is_android_tv:
            return _generate_esn_android_tv(props, wv_force_sec_lev)
        return _generate_esn_android(props, wv_force_sec_lev)
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
        esn_w_split = get_website_esn().split('-', 2)
        if len(esn_w_split) != 3:
            raise ErrorMsg('Cannot generate ESN due to unexpected website ESN')
        init_part = '-'.join(esn_w_split[:2]) + '-'
    esn = init_part
    possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    from secrets import choice
    for _ in range(0, 30):
        esn += choice(possible)
    return esn


def _generate_esn_android(props, wv_force_sec_lev):
    """Generate ESN for Android device"""
    manufacturer = props.get('ro.product.manufacturer', '').upper()
    if not manufacturer:
        LOG.error('Cannot generate ESN ro.product.manufacturer not found')
        return None
    model = props.get('ro.product.model', '').upper()
    if not model:
        LOG.error('Cannot generate ESN ro.product.model not found')
        return None

    device_category = 'T-'  # The default value must be "P",
    # but we force to "T" that should provide 1080p on tablets, this because to determinate if the device fall in
    # to the tablet category we need to know the screen size by DisplayMetrics android API that we do not have access
    # and then check/calculate with the following formula:
    # if 600 <= min(width_px / density, height_px / density):
    #    device_category = 'T-'

    # Device categories (updated 06/10/2022):
    #  Unknown or Phone "P"
    #  Tablet           "T"
    #  Chrome OS Tablet "C"
    #  Setup Box        "B"
    #  Smart Display    "E"

    drm_security_level, system_id = _get_drm_info(wv_force_sec_lev)

    sec_lev = '' if drm_security_level == 'L1' else 'L3-'

    if len(manufacturer) < 5:
        manufacturer += '       '
    manufacturer = manufacturer[:5]
    model = model[:45].strip()

    prod = manufacturer + model
    prod = re.sub(r'[^A-Za-z0-9=-]', '=', prod)

    return 'NFANDROID1-PRV-' + device_category + sec_lev + prod + '-' + system_id + '-' + _create_id64chars()


def _generate_esn_android_tv(props, wv_force_sec_lev):
    """Generate ESN for Android TV device"""
    sdk_version = int(props['ro.build.version.sdk'])
    manufacturer = props.get('ro.product.manufacturer', '').upper()
    if not manufacturer:
        LOG.error('Cannot generate ESN ro.product.manufacturer not found')
        return None
    model = props.get('ro.product.model', '').upper()
    if not model:
        LOG.error('Cannot generate ESN ro.product.model not found')
        return None

    # Netflix Ready Device Platform (NRDP)
    if sdk_version >= 28:
        model_group = props.get('ro.vendor.nrdp.modelgroup', '').upper()
    else:
        model_group = props.get('ro.nrdp.modelgroup', '').upper()

    if not model_group:
        model_group = '0'
    model_group = re.sub(r'[^A-Za-z0-9=-]', '=', model_group)

    if len(manufacturer) < 5:
        manufacturer += '       '
    manufacturer = manufacturer[:5]
    model = model[:45].strip()

    prod = manufacturer + model
    prod = re.sub(r'[^A-Za-z0-9=-]', '=', prod)

    _, system_id = _get_drm_info(wv_force_sec_lev)

    return 'NFANDROID2-PRV-' + model_group + '-' + prod + '-' + system_id + '-' + _create_id64chars()


def _get_drm_info(wv_force_sec_lev):
    drm_security_level = G.LOCAL_DB.get_value('drm_security_level', '', table=TABLE_SESSION)
    system_id = G.LOCAL_DB.get_value('drm_system_id', table=TABLE_SESSION)

    if not system_id:
        raise ErrorMsg('Cannot get DRM system id')

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
    return drm_security_level, system_id


def _create_id64chars():
    # The Android full length ESN include to the end a hashed ID of 64 chars,
    # this value is created from the android app by using the Widevine "deviceUniqueId" property value
    # hashed in various ways, not knowing the correct formula, we create a random value.
    # Starting from 12/2022 this value is mandatory to obtain HD resolutions
    from secrets import token_hex
    return re.sub(r'[^A-Za-z0-9=-]', '=', token_hex(32).upper())
