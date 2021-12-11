# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT (original implementation module)
    Get the UUID of the device

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from resources.lib.globals import G
from resources.lib.utils.logging import LOG
from .device_utils import get_system_platform


def get_crypt_key():
    """
    Lazily generate the crypt key and return it
    """
    if not hasattr(get_crypt_key, 'cached'):
        get_crypt_key.cached = _get_system_uuid()
    return get_crypt_key.cached


def get_random_uuid():
    """
    Generate a random uuid
    :return: a string of a random uuid
    """
    import uuid
    return str(uuid.uuid4())


def get_namespace_uuid(name):
    """
    Generate a namespace uuid
    :return: uuid object
    """
    import uuid
    return uuid.uuid5(uuid.NAMESPACE_DNS, name)


def _get_system_uuid():
    """
    Try to get an uuid from the system, if it's not possible generates a fake uuid
    :return: an uuid converted to MD5
    """
    uuid_value = ''
    if G.ADDON.getSettingBool('credentials_system_encryption'):
        system = get_system_platform()
        if system in ['windows', 'uwp']:
            uuid_value = _get_windows_uuid()
        elif system == 'android':
            uuid_value = _get_android_uuid()
        elif system == 'linux':
            uuid_value = _get_linux_uuid()
        elif system == 'osx':
            # Due to OS restrictions on 'ios' and 'tvos' is not possible to use _get_macos_uuid()
            # See python limits in the wiki development page
            uuid_value = _get_macos_uuid()
        if not uuid_value:
            LOG.debug('It is not possible to get a system UUID creating a new UUID')
            uuid_value = _get_fake_uuid(system not in ['android', 'linux'])
    return get_namespace_uuid(str(uuid_value)).bytes


def _get_windows_uuid():
    # pylint: disable=broad-except
    # pylint: disable=import-error  # Under linux pylint rightly complains
    uuid_value = None
    try:
        import winreg
        registry = winreg.HKEY_LOCAL_MACHINE
        address = 'SOFTWARE\\Microsoft\\Cryptography'
        keyargs = winreg.KEY_READ | winreg.KEY_WOW64_64KEY
        key = winreg.OpenKey(registry, address, 0, keyargs)
        value = winreg.QueryValueEx(key, 'MachineGuid')
        winreg.CloseKey(key)
        uuid_value = value[0]
    except Exception:
        pass
    if not uuid_value:
        try:
            import subprocess
            output = subprocess.check_output(['vol', 'c:'])
            output = output.split()
            uuid_value = output[len(output) - 1:]
        except Exception:
            pass
    return uuid_value


def _get_linux_uuid():
    # pylint: disable=broad-except
    import subprocess
    uuid_value = None
    try:
        uuid_value = subprocess.check_output(['cat', '/etc/machine-id']).decode('utf-8')
    except Exception as exc:
        import traceback
        LOG.error('_get_linux_uuid first attempt returned: {}', exc)
        LOG.error(traceback.format_exc())
    if not uuid_value:
        try:
            uuid_value = subprocess.check_output(['cat', '/var/lib/dbus/machine-id']).decode('utf-8')
        except Exception as exc:
            LOG.error('_get_linux_uuid second attempt returned: {}', exc)
    return uuid_value


def _get_android_uuid():
    # pylint: disable=broad-except
    import subprocess
    import re
    values = ''
    try:
        # Due to the new android security we cannot get any type of serials
        sys_prop = ['ro.product.board', 'ro.product.brand', 'ro.product.device', 'ro.product.locale'
                    'ro.product.manufacturer', 'ro.product.model', 'ro.product.platform',
                    'persist.sys.timezone', 'persist.sys.locale', 'net.hostname']
        # Warning net.hostname property starting from android 10 is deprecated return empty
        with subprocess.Popen(['/system/bin/getprop'], stdout=subprocess.PIPE) as proc:
            output_data = proc.communicate()[0].decode('utf-8')
        list_values = output_data.splitlines()
        for value in list_values:
            value_splitted = re.sub(r'\[|\]|\s', '', value).split(':')
            if value_splitted[0] in sys_prop:
                values += value_splitted[1]
    except Exception:
        pass
    return values.encode('utf-8')


def _get_macos_uuid():
    # pylint: disable=broad-except
    import subprocess
    sp_dict_values = None
    try:
        with subprocess.Popen(
                ['/usr/sbin/system_profiler', 'SPHardwareDataType', '-detaillevel', 'full', '-xml'],
                stdout=subprocess.PIPE) as proc:
            output_data = proc.communicate()[0].decode('utf-8')
        if output_data:
            sp_dict_values = _parse_osx_xml_plist_data(output_data)
    except Exception as exc:
        LOG.debug('Failed to fetch OSX/IOS system profile {}', exc)
    if sp_dict_values:
        if 'UUID' in sp_dict_values:
            return sp_dict_values['UUID']
        if 'serialnumber' in sp_dict_values:
            return sp_dict_values['serialnumber']
    return None


def _parse_osx_xml_plist_data(data):
    import plistlib
    import re
    dict_values = {}
    xml_data = plistlib.loads(data)
    items_dict = xml_data[0]['_items'][0]
    r = re.compile(r'.*UUID.*')  # Find to example "platform_UUID" key
    uuid_keys = list(filter(r.match, list(items_dict.keys())))
    if uuid_keys:
        dict_values['UUID'] = items_dict[uuid_keys[0]]
    if not uuid_keys:
        r = re.compile(r'.*serial.*number.*')  # Find to example "serial_number" key
        serialnumber_keys = list(filter(r.match, list(items_dict.keys())))
        if serialnumber_keys:
            dict_values['serialnumber'] = items_dict[serialnumber_keys[0]]
    return dict_values


def _get_fake_uuid(with_hostname=True):
    """
    Generate a uuid based on various system information
    """
    import xbmc
    import platform
    list_values = [xbmc.getInfoLabel('System.Memory(total)')]
    if with_hostname:
        # Note: on linux systems hostname content may change after every system update
        try:
            list_values.append(platform.node())
        except Exception:  # pylint: disable=broad-except
            # Due to OS restrictions on 'ios' and 'tvos' an error happen
            # See python limits in the wiki development page
            pass
    return '_'.join(list_values)
