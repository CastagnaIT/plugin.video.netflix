# -*- coding: utf-8 -*-
# pylint: disable=unused-import
"""Common plugin operations and utilities"""
from __future__ import unicode_literals

import sys
import os
import json
from functools import wraps
from datetime import datetime, timedelta

import xbmc
from xbmc import LOGDEBUG, LOGINFO, LOGWARNING, LOGERROR
import xbmcaddon
import xbmcvfs

try:
    import cPickle as pickle
except ImportError:
    import pickle

ADDON = xbmcaddon.Addon()
PLUGIN = ADDON.getAddonInfo('name')
VERSION = ADDON.getAddonInfo('version')
DEFAULT_FANART = ADDON.getAddonInfo('fanart')
DATA_PATH = xbmc.translatePath(ADDON.getAddonInfo('profile'))
COOKIE_PATH = DATA_PATH + 'COOKIE'
BASE_URL = sys.argv[0]
try:
    PLUGIN_HANDLE = int(sys.argv[1])
except IndexError:
    PLUGIN_HANDLE = None

if not xbmcvfs.exists(DATA_PATH):
    xbmcvfs.mkdir(DATA_PATH)

class Signals(object):
    """Signal names for use with AddonSignals"""
    # pylint: disable=too-few-public-methods
    PLAYBACK_INITIATED = 'playback_initiated'

class PersistentStorage(object):
    """
    Key-Value storage with a backing file on disk.
    Reads entire dict structure into memory on first access and updates
    the backing file with each changed entry.

    IMPORTANT: Changes to mutable objects inserted into the key-value-store
    are not automatically written to disk. You need to call commit() to
    persist these changes.
    """
    def __init__(self, storage_id):
        self.storage_id = storage_id
        self.backing_file = os.path.join(DATA_PATH, self.storage_id + '.ndb')
        self._contents = {}
        self._dirty = True
        log('Instantiated {}'.format(self.storage_id))

    def __getitem__(self, key):
        log('Getting {}'.format(key))
        return self.contents[key]

    def __setitem__(self, key, value):
        log('Setting {} to {}'.format(key, value))
        self._contents[key] = value
        self.commit()
        self._dirty = True

    @property
    def contents(self):
        """
        The contents of the storage file
        """
        if self._dirty:
            self._load_from_disk()
        return self._contents

    def get(self, key, default=None):
        """
        Return the value associated with key. If key does not exist,
        return default (defaults to None)
        """
        return self.contents.get(key, default)

    def commit(self):
        """
        Write current contents to disk
        """
        file_handle = xbmcvfs.File(self.backing_file, 'wb')
        pickle.dump(self._contents, file_handle)
        file_handle.close()
        log('Committed changes to backing file')

    def clear(self):
        """
        Clear contents and backing file
        """
        self._contents = {}
        self.commit()

    def _load_from_disk(self):
        log('Trying to load contents from disk')
        if xbmcvfs.exists(self.backing_file):
            file_handle = xbmcvfs.File(self.backing_file, 'rb')
            self._contents = pickle.loads(file_handle.read())
            self._dirty = False
            file_handle.close()
            log('Loaded contents from backing file: {}'.format(self._contents))
        else:
            log('Backing file does not exist')

__BLOCK_SIZE__ = 32
__CRYPT_KEY__ = None

def __crypt_key():
    """
    Lazily generate the crypt key and return it
    """
    # pylint: disable=global-statement
    global __CRYPT_KEY__
    if not __CRYPT_KEY__:
        __CRYPT_KEY__ = __uniq_id()
    return __CRYPT_KEY__

def __uniq_id():
    """
    Returns a unique id based on the devices MAC address
    """
    import uuid
    mac = uuid.getnode()
    if (mac >> 40) % 2:
        from platform import node
        mac = node()
    return uuid.uuid5(uuid.NAMESPACE_DNS, str(mac)).bytes

def encrypt_credential(raw):
    """
    Encodes data

    :param data: Data to be encoded
    :type data: str
    :returns:  string -- Encoded data
    """
    # pylint: disable=invalid-name,import-error
    import base64
    from Cryptodome import Random
    from Cryptodome.Cipher import AES
    from Cryptodome.Util import Padding
    raw = bytes(Padding.pad(data_to_pad=raw, block_size=__BLOCK_SIZE__))
    iv = Random.new().read(AES.block_size)
    cipher = AES.new(__crypt_key(), AES.MODE_CBC, iv)
    return base64.b64encode(iv + cipher.encrypt(raw))

def decrypt_credential(enc):
    """
    Decodes data

    :param data: Data to be decoded
    :type data: str
    :returns:  string -- Decoded data
    """
    # pylint: disable=invalid-name,import-error
    import base64
    from Cryptodome.Cipher import AES
    from Cryptodome.Util import Padding
    enc = base64.b64decode(enc)
    iv = enc[:AES.block_size]
    cipher = AES.new(__uniq_id(), AES.MODE_CBC, iv)
    decoded = Padding.unpad(
        padded_data=cipher.decrypt(enc[AES.block_size:]),
        block_size=__BLOCK_SIZE__).decode('utf-8')
    return decoded

def get_credentials():
    """
    Retrieve stored account credentials.
    :return: The stored account credentials or an empty dict if none exist.
    """
    email = ADDON.getSetting('email')
    password = ADDON.getSetting('password')

    if '@' in email:
        set_credentials(email, password)
        return {'email': email, 'password': password}

    return {
        'email': decrypt_credential(email) if email and password else '',
        'password': decrypt_credential(password) if email and password else ''
    }

def set_credentials(email, password):
    """
    Encrypt account credentials and save them to the settings.
    Does nothing if either email or password are not supplied.
    """
    if email and password:
        ADDON.setSetting('email', encrypt_credential(email))
        ADDON.setSetting('password', encrypt_credential(password))

def get_esn():
    """Get the ESN from settings"""
    return ADDON.getSetting('esn')

def set_esn(esn):
    """
    Set the ESN in settings if it hasn't been set yet.
    Return True if the new ESN has been set, False otherwise
    """
    if not get_esn() and esn:
        ADDON.setSetting('esn', esn)
        return True
    return False

def flush_settings():
    """Reload the ADDON"""
    # pylint: disable=global-statement
    global ADDON
    ADDON = xbmcaddon.Addon()

def select_port(server):
    """Select a port for a server and store it in the settings"""
    port = select_unused_port()
    ADDON.setSetting('{}_service_port'.format(server), str(port))
    log('[{}] Picked Port: {}'.format(server.upper(), port))
    return port

def log(msg, level=LOGDEBUG):
    """Log a message to the Kodi logfile"""
    if isinstance(msg, Exception):
        level = LOGERROR
    xbmc.log(
        '[{identifier}] {msg}'.format(identifier=ADDON.getAddonInfo('id'),
                                      msg=msg),
        level)

def check_folder_path(path):
    """
    Check if folderpath ends with path delimator
    If not correct it (makes sure xbmcvfs.exists is working correct)
    """
    end = ''
    if isinstance(path, unicode):
        check = path.encode('ascii', 'ignore')
        if '/' in check and not str(check).endswith('/'):
            end = u'/'
        if '\\' in check and not str(check).endswith('\\'):
            end = u'\\'
    else:
        if '/' in path and not str(path).endswith('/'):
            end = '/'
        if '\\' in path and not str(path).endswith('\\'):
            end = '\\'
    return path + end

def file_exists(filename, data_path=DATA_PATH):
    """
    Checks if a given file exists
    :param filename: The filename
    :return: True if so
    """
    return xbmcvfs.exists(path=data_path + filename)

def save_file(filename, content, data_path=DATA_PATH):
    """
    Saves the given content under given filename
    :param filename: The filename
    :param content: The content of the file
    """
    file_handle = xbmcvfs.File(filepath=data_path + filename, mode='w')
    file_handle.write(content.encode('utf-8'))
    file_handle.close()

def load_file(filename, data_path=DATA_PATH):
    """
    Loads the content of a given filename
    :param filename: The file to load
    :return: The content of the file
    """
    file_handle = xbmcvfs.File(filepath=data_path + filename)
    file_content = file_handle.read()
    file_handle.close()
    return file_content

def list_dir(data_path=DATA_PATH):
    """
    List the contents of a folder
    :return: The contents of the folder
    """
    return xbmcvfs.listdir(data_path)

def noop(**kwargs):
    """Takes everything, does nothing, classic no operation function"""
    return kwargs

def find_episode(episode_id, seasons):
    """
    Get metadata for a specific episode from within a nested
    metadata dict.
    :return: Episode metadata or an empty dict if the episode could not
    be found.
    """
    for season in seasons:
        for episode in season['episodes']:
            if str(episode['id']) == episode_id:
                return episode
    return {}

def update_library_item_details(dbtype, dbid, details):
    """
    Update properties of an item in the Kodi library
    """
    method = 'VideoLibrary.Set{}Details'.format(dbtype.capitalize())
    params = {'{}id'.format(dbtype): dbid}
    params.update(details)
    return json_rpc(method, params)

def get_class_methods(class_item=None):
    """
    Returns the class methods of agiven class object

    :param class_item: Class item to introspect
    :type class_item: object
    :returns: list -- Class methods
    """
    from types import FunctionType
    _type = FunctionType
    return [x for x, y in class_item.__dict__.items() if isinstance(y, _type)]

def get_user_agent():
    """
    Determines the user agent string for the current platform.
    Needed to retrieve a valid ESN (except for Android, where the ESN can
    be generated locally)

    :returns: str -- User agent string
    """
    import platform
    chrome_version = 'Chrome/59.0.3071.115'
    base = 'Mozilla/5.0 '
    base += '%PL% '
    base += 'AppleWebKit/537.36 (KHTML, like Gecko) '
    base += '%CH_VER% Safari/537.36'.replace('%CH_VER%', chrome_version)
    system = platform.system()
    # Mac OSX
    if system == 'Darwin':
        return base.replace('%PL%', '(Macintosh; Intel Mac OS X 10_10_1)')
    # Windows
    if system == 'Windows':
        return base.replace('%PL%', '(Windows NT 6.1; WOW64)')
    # ARM based Linux
    if platform.machine().startswith('arm'):
        return base.replace('%PL%', '(X11; CrOS armv7l 7647.78.0)')
    # x86 Linux
    return base.replace('%PL%', '(X11; Linux x86_64)')

def json_rpc(method, params=None):
    """
    Executes a JSON-RPC in Kodi

    :param method: The JSON-RPC method to call
    :type method: string
    :param params: The parameters of the method call (optional)
    :type params: dict
    :returns: dict -- Method call result
    """
    request_data = {'jsonrpc': '2.0', 'method': method, 'id': 1,
                    'params': params or {}}
    request = json.dumps(request_data)
    response = json.loads(unicode(xbmc.executeJSONRPC(request), 'utf-8',
                                  errors='ignore'))
    if 'error' in response:
        raise IOError('JSONRPC-Error {}: {}'
                      .format(response['error']['code'],
                              response['error']['message']))
    return response['result']

def logdetails(func):
    """
    Log decarator that is used to annotate methods & output everything to
    the Kodi debug log

    :param delay: retry delay in sec
    :type delay: int
    :returns:  string -- Devices MAC address
    """
    name = func.func_name

    @wraps(func)
    def wrapped(*args, **kwargs):
        """Wrapper function to maintain correct stack traces"""
        that = args[0]
        class_name = that.__class__.__name__
        arguments = [':{} = {}:'.format(key, value)
                     for key, value in kwargs.iteritems()
                     if key not in ['account', 'credentials']]
        if arguments:
            log('{cls}::{method} called with arguments {args}'
                .format(cls=class_name, method=name, args=''.join(arguments)))
        else:
            log('{cls}::{method} called'.format(cls=class_name, method=name))
        result = func(*args, **kwargs)
        log('{cls}::{method} return {result}'
            .format(cls=class_name, method=name, result=result))
        return result

    wrapped.__doc__ = func.__doc__
    return wrapped

def strp(value, form):
    """
    Helper function to safely create datetime objects from strings

    :return: datetime - parsed datetime object
    """
    # pylint: disable=broad-except
    from time import strptime
    def_value = datetime.utcfromtimestamp(0)
    try:
        return datetime.strptime(value, form)
    except TypeError:
        try:
            return datetime(*(strptime(value, form)[0:6]))
        except ValueError:
            return def_value
    except Exception:
        return def_value

def _update_running():
    update = ADDON.getSetting('update_running') or None
    if update:
        starttime = strp(update, '%Y-%m-%d %H:%M')
        if (starttime + timedelta(hours=6)) <= datetime.now():
            ADDON.setSetting('update_running', 'false')
            log('Canceling previous library update - duration > 6 hours',
                LOGWARNING)
        else:
            log('DB Update already running')
            return True
    return False

def update_library():
    """
    Update the local Kodi library with new episodes of exported shows
    """
    if not _update_running():
        log('Triggering library update', LOGINFO)
        xbmc.executebuiltin(
            ('XBMC.RunPlugin(plugin://{}/?action=export-new-episodes'
             '&inbackground=True)')
            .format(ADDON.getAddonInfo('id')))

def select_unused_port():
    """
    Helper function to select an unused port on the host machine

    :return: int - Free port
    """
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('127.0.0.1', 0))
    _, port = sock.getsockname()
    sock.close()
    return port
