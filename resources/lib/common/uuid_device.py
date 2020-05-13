# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT (original implementation module)
    Get the UUID of the device

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

from resources.lib.globals import g
from .device_utils import get_system_platform
from .logging import debug, error

try:  # Python 2
    unicode
except NameError:  # Python 3
    unicode = str  # pylint: disable=redefined-builtin

__CRYPT_KEY__ = None


def get_crypt_key():
    """
    Lazily generate the crypt key and return it
    """
    # pylint: disable=global-statement
    global __CRYPT_KEY__
    if not __CRYPT_KEY__:
        __CRYPT_KEY__ = _get_system_uuid()
    return __CRYPT_KEY__


def get_random_uuid():
    """
    Generate a random uuid
    :return: a string of a random uuid
    """
    import uuid
    return unicode(uuid.uuid4())


def _get_system_uuid():
    """
    Try to get an uuid from the system, if it's not possible generates a fake uuid
    :return: an uuid converted to MD5
    """
    import uuid
    uuid_value = None
    system = get_system_platform()
    if system in ['windows', 'uwp']:
        uuid_value = _get_windows_uuid()
    elif system == 'android':
        uuid_value = _get_android_uuid()
    elif system in ['linux', 'linux raspberrypi']:
        uuid_value = _get_linux_uuid()
    elif system == 'osx':
        # Due to OS restrictions on 'ios' and 'tvos' is not possible to use _get_macos_uuid()
        # See python limits in the wiki development page
        uuid_value = _get_macos_uuid()
    if not uuid_value:
        debug('It is not possible to get a system UUID creating a new UUID')
        uuid_value = _get_fake_uuid(system not in ['android', 'linux', 'linux raspberrypi'])
    return uuid.uuid5(uuid.NAMESPACE_DNS, str(uuid_value)).bytes


def _get_windows_uuid():
    # pylint: disable=broad-except
    # pylint: disable=no-member
    uuid_value = None
    try:
        try:  # Python 2
            import _winreg as winreg
        except ImportError:  # Python 3
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
        uuid_value = subprocess.check_output(['cat', '/var/lib/dbus/machine-id']).decode('utf-8')
    except Exception as exc:
        import traceback
        error('_get_linux_uuid first attempt returned: {}', exc)
        error(g.py2_decode(traceback.format_exc(), 'latin-1'))
    if not uuid_value:
        try:
            # Fedora linux
            uuid_value = subprocess.check_output(['cat', '/etc/machine-id']).decode('utf-8')
        except Exception as exc:
            error('_get_linux_uuid second attempt returned: {}', exc)
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
        proc = subprocess.Popen(['/system/bin/getprop'], stdout=subprocess.PIPE)
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
        proc = subprocess.Popen(
            ['/usr/sbin/system_profiler', 'SPHardwareDataType', '-detaillevel', 'full', '-xml'],
            stdout=subprocess.PIPE)
        output_data = proc.communicate()[0].decode('utf-8')
        if output_data:
            sp_dict_values = _parse_osx_xml_plist_data(output_data)
    except Exception as exc:
        debug('Failed to fetch OSX/IOS system profile {}'.format(exc))
    if sp_dict_values:
        if 'UUID' in list(sp_dict_values.keys()):
            return sp_dict_values['UUID']
        if 'serialnumber' in list(sp_dict_values.keys()):
            return sp_dict_values['serialnumber']
    return None


def _parse_osx_xml_plist_data(data):
    import plistlib
    import re
    dict_values = {}
    try:  # Python 2
        xml_data = plistlib.readPlistFromString(data)
    except AttributeError:  # Python => 3.4
        # pylint: disable=no-member
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
