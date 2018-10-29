# -*- coding: utf-8 -*-
# pylint: disable=unused-import
"""Common plugin operations and utilities"""
from __future__ import unicode_literals

import sys
import os
import json
import traceback
from functools import wraps
from datetime import datetime, timedelta
from urlparse import urlparse, parse_qsl
from urllib import urlencode

import xbmc
import xbmcaddon
import xbmcgui
import AddonSignals

# Global vars are initialized in init_globals
# Commonly used addon attributes from Kodi
ADDON = None
ADDON_ID = None
PLUGIN = None
VERSION = None
DEFAULT_FANART = None
ICON = None
DATA_PATH = None
COOKIE_PATH = None
CACHE_TTL = None
CACHE_METADATA_TTL = None

# Information about the current plugin instance
URL = None
PLUGIN_HANDLE = None
BASE_URL = None
PATH = None
PARAM_STRING = None
REQUEST_PARAMS = None

KNOWN_LIST_TYPES = ['queue', 'topTen', 'netflixOriginals', 'continueWatching',
                    'trendingNow', 'newRelease', 'popularTitles']
MISC_CONTEXTS = {
    'genres': {'label_id': 30010,
               'description_id': 30093,
               'icon': 'DefaultGenre.png',
               'contexts': 'genre'},
    'recommendations': {'label_id': 30001,
                        'description_id': 30094,
                        'icon': 'DefaultUser.png',
                        'contexts': ['similars', 'becauseYouAdded']}
}

MODE_DIRECTORY = 'directory'
MODE_HUB = 'hub'
MODE_ACTION = 'action'
MODE_PLAY = 'play'
MODE_LIBRARY = 'library'

def init_globals(argv):
    """Initialized globally used module variables.
    Needs to be called at start of each plugin instance!
    This is an ugly hack because Kodi doesn't execute statements defined on
    module level if reusing a language invoker."""
    # pylint: disable=global-statement
    global ADDON, ADDON_ID, PLUGIN, VERSION, DEFAULT_FANART, ICON, DATA_PATH, \
           COOKIE_PATH, CACHE_TTL, CACHE_METADATA_TTL
    ADDON = xbmcaddon.Addon()
    ADDON_ID = ADDON.getAddonInfo('id')
    PLUGIN = ADDON.getAddonInfo('name')
    VERSION = ADDON.getAddonInfo('version')
    DEFAULT_FANART = ADDON.getAddonInfo('fanart')
    ICON = ADDON.getAddonInfo('icon')
    DATA_PATH = xbmc.translatePath(ADDON.getAddonInfo('profile'))
    COOKIE_PATH = DATA_PATH + 'COOKIE'
    CACHE_TTL = ADDON.getSettingInt('cache_ttl') * 60
    CACHE_METADATA_TTL = ADDON.getSettingInt('cache_metadata_ttl') * 60

    global URL, PLUGIN_HANDLE, BASE_URL, PATH, PARAM_STRING, REQUEST_PARAMS
    URL = urlparse(argv[0])
    try:
        PLUGIN_HANDLE = int(argv[1])
    except IndexError:
        PLUGIN_HANDLE = 0
    BASE_URL = '{scheme}://{netloc}'.format(scheme=URL[0], netloc=URL[1])
    PATH = URL[2][1:]
    try:
        PARAM_STRING = argv[2][1:]
    except IndexError:
        PARAM_STRING = ''
    REQUEST_PARAMS = dict(parse_qsl(PARAM_STRING))

    try:
        os.mkdir(DATA_PATH)
    except OSError:
        pass

init_globals(sys.argv)

class MissingCredentialsError(Exception):
    """There are no stored credentials to load"""
    pass

class InvalidVideoId(Exception):
    """The provided video id is not valid"""
    pass

class VideoId(object):
    """Universal representation of a video id. Video IDs can be of multiple
    types:
    - movie: a single identifier only for movieid, all other values must be
             None
    - show: a single identifier only for tvshowid, all other values must be
            None
    - season: identifiers for seasonid and tvshowid, all other values must
              be None
    - episode: identifiers for episodeid, seasonid and tvshowid, all other
               values must be None
    - no type: a single identifier only for videoid. If this is used, there's
               no validation and other supplied values will be ignored."""
    # pylint: disable=too-many-arguments
    MOVIE = 'movie'
    SHOW = 'show'
    SEASON = 'season'
    EPISODE = 'episode'
    UNSPECIFIED = 'unspecified'

    REPR_FORMAT = ('{mediatype}(videoid={videoid},movieid={movieid},'
                   'episodeid={episodeid},seasonid={seasonid},'
                   'tvshowid={tvshowid})')

    def __init__(self, movieid=None, episodeid=None, seasonid=None,
                 tvshowid=None, videoid=None):
        if videoid:
            self.videoid = videoid
            self.id_values = (None, None, None, None)
        else:
            self.videoid = None
            self.id_values = (movieid, episodeid, seasonid, tvshowid)
            for id_index in range(0, len(self.id_values) - 1):
                if self._validate(id_index):
                    break

    @classmethod
    def from_path(cls, pathitems):
        """Create a VideoId instance from pathitems"""
        if pathitems[0] == 'movie':
            return cls(movieid=pathitems[1])
        elif pathitems[0] == 'show':
            return cls(tvshowid=pathitems[1],
                       seasonid=pathitems[3] if len(pathitems) > 3 else None,
                       episodeid=pathitems[5] if len(pathitems) > 5 else None)
        return cls(videoid=pathitems[0])

    @property
    def value(self):
        """The value of this videoId"""
        return (self.videoid
                if self.videoid
                else next(id_value for id_value in self.id_values if id_value))

    @property
    def movieid(self):
        """The seasonid value, if it exists"""
        return None if self.videoid else self.id_values[0]

    @property
    def episodeid(self):
        """The seasonid value, if it exists"""
        return None if self.videoid else self.id_values[1]

    @property
    def seasonid(self):
        """The seasonid value, if it exists"""
        return None if self.videoid else self.id_values[2]

    @property
    def tvshowid(self):
        """The tvshowid value, if it exists"""
        return None if self.videoid else self.id_values[3]

    @property
    def mediatype(self):
        """The mediatype this VideoId instance represents.
        Either movie, show, season, episode or unknown"""
        return (self.UNSPECIFIED
                if self.videoid
                else (self.MOVIE, self.EPISODE, self.SEASON, self.SHOW)[
                    next(i
                         for i, v in enumerate(self.id_values)
                         if v is not None)])

    def to_path(self):
        """Generate a valid pathitems list (['show', tvshowid, ...]) from
        this instance"""
        if self.videoid:
            return [self.videoid]
        if self.movieid:
            return [self.MOVIE, self.movieid]

        pathitems = [self.SHOW, self.tvshowid]
        if self.seasonid:
            pathitems.extend([self.SEASON, self.seasonid])
        if self.episodeid:
            pathitems.extend([self.EPISODE, self.episodeid])
        return pathitems

    def to_list(self):
        """Generate a list representation that can be used with get_path"""
        if self.videoid:
            return self.videoid
        path = [id_part for id_part in self.id_values if id_part]
        if len(path) > 1:
            path.reverse()
        return path

    def to_dict(self):
        """Return a dict containing the relevant properties of this
        instance"""
        result = {'mediatype': self.mediatype}
        if self.videoid:
            result['videoid'] = self.videoid
            return result
        if self.movieid:
            result['movieid'] = self.movieid
            return result
        result.update({prop: self.__getattribute__(prop)
                       for prop in ['tvshowid', 'seasonid', 'episodeid']
                       if self.__getattribute__(prop) is not None})
        return result

    def derive_season(self, seasonid):
        """Return a new VideoId instance that represents the given season
        of this show. Raises InvalidVideoId is this instance does not
        represent a show."""
        if self.mediatype != VideoId.SHOW:
            raise InvalidVideoId('Cannot derive season VideoId from {}'
                                 .format(self))
        return type(self)(tvshowid=self.tvshowid, seasonid=seasonid)

    def derive_episode(self, episodeid):
        """Return a new VideoId instance that represents the given episode
        of this season. Raises InvalidVideoId is this instance does not
        represent a season."""
        if self.mediatype != VideoId.SEASON:
            raise InvalidVideoId('Cannot derive episode VideoId from {}'
                                 .format(self))
        return type(self)(tvshowid=self.tvshowid, seasonid=self.seasonid,
                          episodeid=episodeid)

    def _validate(self, index):
        if self.id_values[index]:
            if ((not all(v is None for v in self.id_values[1:])
                 if index == 0
                 else None in self.id_values[index:])):
                raise InvalidVideoId(self.id_values)
            return True  # Validation successful
        if index == len(self.id_values):
            raise InvalidVideoId(self.id_values)
        return False  # Validation does not apply

    def __str__(self):
        return '{}_{}'.format(self.mediatype, self.value)

    def __hash__(self):
        return hash(str(self))

    def __eq__(self, other):
        return (self.videoid == other.videoid and
                self.id_values == other.id_values)

    def __neq__(self, other):
        return not self.__eq__(other)

class Signals(object):
    """Signal names for use with AddonSignals"""
    # pylint: disable=too-few-public-methods
    PLAYBACK_INITIATED = 'playback_initiated'
    ESN_CHANGED = 'esn_changed'

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
        debug('Instantiated {}'.format(self.storage_id))

    def __del__(self):
        debug('Destroying storage instance {}'.format(self.storage_id))
        self.commit()

    def __getitem__(self, key):
        return self.contents[key]

    def __setitem__(self, key, value):
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
        with open(self.backing_file, 'w') as file_handle:
            json.dump(self._contents, file_handle)
        debug('Committed changes to backing file')

    def clear(self):
        """
        Clear contents and backing file
        """
        self._contents = {}
        self.commit()

    def _load_from_disk(self):
        debug('Trying to load contents from disk')
        try:
            with open(self.backing_file, 'r') as file_handle:
                self._contents = json.load(file_handle)
        except IOError:
            error('Backing file does not exist or is not accessible')
        self._dirty = False
        debug('Loaded contents from backing file: {}'.format(self._contents))

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
    verify_credentials(email, password)
    try:
        return {
            'email': decrypt_credential(email),
            'password': decrypt_credential(password)
        }
    except ValueError:
        raise MissingCredentialsError(
            'Existing credentials could not be decrypted')

def set_credentials(email, password):
    """
    Encrypt account credentials and save them to the settings.
    Does nothing if either email or password are not supplied.
    """
    if email and password:
        ADDON.setSetting('email', encrypt_credential(email))
        ADDON.setSetting('password', encrypt_credential(password))

def verify_credentials(email, password):
    """Verify credentials for plausibility"""
    if not email or not password:
        raise MissingCredentialsError()

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

def select_port():
    """Select a port for a server and store it in the settings"""
    port = select_unused_port()
    ADDON.setSetting('msl_service_port', str(port))
    log('[MSL] Picked Port: {}'.format(port))
    return port

def log(msg, level=xbmc.LOGDEBUG):
    """Log a message to the Kodi logfile"""
    xbmc.log(
        '[{identifier}] {msg}'.format(identifier=ADDON.getAddonInfo('id'),
                                      msg=msg),
        level)

def debug(msg='{exc}', exc=None):
    """
    Log a debug message.
    If msg contains a format placeholder for exc and exc is not none,
    exc will be formatted into the message.
    """
    log(msg.format(exc=exc) if exc is not None and '{exc}' in msg else msg,
        xbmc.LOGDEBUG)

def info(msg='{exc}', exc=None):
    """
    Log an info message.
    If msg contains a format placeholder for exc and exc is not none,
    exc will be formatted into the message.
    """
    log(msg.format(exc=exc) if exc is not None and '{exc}' in msg else msg,
        xbmc.LOGINFO)

def warn(msg='{exc}', exc=None):
    """
    Log a warning message.
    If msg contains a format placeholder for exc and exc is not none,
    exc will be formatted into the message.
    """
    log(msg.format(exc=exc) if exc is not None and '{exc}' in msg else msg,
        xbmc.LOGWARNING)

def error(msg='{exc}', exc=None):
    """
    Log an error message.
    If msg contains a format placeholder for exc and exc is not none,
    exc will be formatted into the message.
    """
    log(msg.format(exc=exc) if exc is not None and '{exc}' in msg else msg,
        xbmc.LOGERROR)

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
    return os.path.exists(data_path + filename)

def save_file(filename, content, data_path=DATA_PATH, mode='w'):
    """
    Saves the given content under given filename
    :param filename: The filename
    :param content: The content of the file
    """
    with open(data_path + filename, mode) as file_handle:
        file_handle.write(content.encode('utf-8'))

def load_file(filename, data_path=DATA_PATH, mode='r'):
    """
    Loads the content of a given filename
    :param filename: The file to load
    :return: The content of the file
    """
    with open(data_path + filename, mode) as file_handle:
        return file_handle.read()

def list_dir(data_path=DATA_PATH):
    """
    List the contents of a folder
    :return: The contents of the folder
    """
    return os.listdir(data_path)

def noop(**kwargs):
    """Takes everything, does nothing, classic no operation function"""
    return kwargs

def find_season(season_id, seasons, raise_exc=True):
    """
    Get metadata for a specific season from within a nested
    metadata dict.
    :return: Season metadata. Raises KeyError if metadata for season_id
    does not exist.
    """
    for season in seasons:
        if str(season['id']) == season_id:
            return season
    if raise_exc:
        raise KeyError('Metadata for season {} does not exist'
                       .format(season_id))
    else:
        return {}

def find_episode(episode_id, seasons, raise_exc=True):
    """
    Get metadata for a specific episode from within a nested
    metadata dict.
    :return: Episode metadata. Raises KeyError if metadata for episode_id
    does not exist.
    """
    for season in seasons:
        for episode in season['episodes']:
            if str(episode['id']) == episode_id:
                return episode
    if raise_exc:
        raise KeyError('Metadata for episode {} does not exist'
                       .format(episode_id))
    else:
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
    return [x
            for x, y in class_item.__dict__.iteritems()
            if isinstance(y, _type)]

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
            warn('Canceling previous library update - duration > 6 hours')
        else:
            log('DB Update already running')
            return True
    return False

def update_library():
    """
    Update the local Kodi library with new episodes of exported shows
    """
    if not _update_running():
        info('Triggering library update')
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

def get_path(path, search_space, include_key=False):
    """Retrieve a value from a nested dict by following the path.
    Throws KeyError if any key along the path does not exist"""
    if not isinstance(path, (tuple, list)):
        path = [path]
    current_value = search_space[path[0]]
    if len(path) == 1:
        return (path[0], current_value) if include_key else current_value
    return get_path(path[1:], current_value, include_key)

def get_path_safe(path, search_space, include_key=False, default=None):
    """Retrieve a value from a nested dict by following the path.
    Returns default if any key in the path does not exist."""
    try:
        return get_path(path, search_space, include_key)
    except KeyError:
        return default

def remove_path(path, search_space, remove_remnants=True):
    """Remove a value from a nested dict by following a path.
    Also removes remaining empty dicts in the hierarchy if remove_remnants
    is True"""
    if not isinstance(path, (tuple, list)):
        path = [path]
    if len(path) == 1:
        del search_space[path[0]]
    else:
        remove_path(path[1:], search_space[path[0]])
        if remove_remnants and not search_space[path[0]]:
            del search_space[path[0]]

def get_multiple_paths(path, search_space, default=None):
    """Retrieve multiple values from a nested dict by following the path.
    The path may branch into multiple paths at any point.
    A branch point is a list of different keys to follow down the path.
    Returns a nested dict structure with nested dicts for each branch point in
    the path. This essentially reduces the original nested dict by removing
    those layers that only have one key and keys not specified in the branch
    point. Keys specified in branch points that do not exist in the search
    space are silently ignored"""
    if not isinstance(search_space, (dict, list)):
        return default
    if isinstance(path[0], list):
        return {k: get_multiple_paths([k] + path[1:], search_space, default)
                for k in path[0]
                if k in search_space}
    current_value = search_space.get(path[0], default)
    return (current_value
            if len(path) == 1
            else get_multiple_paths(path[1:], current_value, default))

def register_slot(callback, signal=None):
    """Register a callback with AddonSignals for return calls"""
    name = signal if signal else _signal_name(callback)
    AddonSignals.registerSlot(
        signaler_id=ADDON_ID,
        signal=name,
        callback=callback)
    debug('Registered AddonSignals slot {} to {}'.format(name, callback))

def unregister_slot(callback, signal=None):
    """Remove a registered callback from AddonSignals"""
    name = signal if signal else _signal_name(callback)
    AddonSignals.unRegisterSlot(
        signaler_id=ADDON_ID,
        signal=name)
    debug('Unregistered AddonSignals slot {}'.format(name))

def send_signal(signal, data=None):
    """Send a signal via AddonSignals"""
    AddonSignals.sendSignal(
        source_id=ADDON_ID,
        signal=signal,
        data=data)

def make_call(callname, data=None):
    """Make a call via AddonSignals and wait for it to return.
    The contents of data will be expanded to kwargs and passed into the target
    function."""
    result = AddonSignals.makeCall(
        source_id=ADDON_ID,
        signal=callname,
        data=data,
        timeout_ms=10000)
    if isinstance(result, dict) and 'error' in result:
        msg = ('AddonSignals call {callname} returned {error}: {message}'
               .format(callname, **result))
        error(msg)
        raise Exception(msg)
    elif result is None:
        raise Exception('AddonSignals call timed out')
    return result

def addonsignals_return_call(func):
    """Makes func return callable through AddonSignals and
    handles catching, conversion and forwarding of exceptions"""
    @wraps(func)
    def make_return_call(instance, data):
        """Makes func return callable through AddonSignals and
        handles catching, conversion and forwarding of exceptions"""
        # pylint: disable=broad-except
        try:
            if isinstance(data, dict):
                result = func(instance, **data)
            elif data is not None:
                result = func(instance, data)
            else:
                result = func(instance)
        except Exception as exc:
            error('AddonSignals callback raised exception: {exc}', exc)
            error(traceback.format_exc())
            result = {
                'error': exc.__class__.__name__,
                'message': exc.__unicode__()
            }
        # Do not return None or AddonSignals will keep waiting till timeout
        if result is None:
            result = False
        AddonSignals.returnCall(
            signal=_signal_name(func), source_id=ADDON_ID, data=result)
    return make_return_call

def _signal_name(func):
    return func.__name__

def build_url(pathitems=None, videoid=None, params=None, mode=None):
    """Build a plugin URL from pathitems and query parameters.
    Add videoid to the path if it's present."""
    pathitems = pathitems or []
    if videoid:
        pathitems.extend(videoid.to_path())
    elif not pathitems:
        raise ValueError('Either pathitems or videoid must be set.')
    if mode:
        pathitems.insert(0, mode)
    return '{netloc}/{path}{qs}'.format(
        netloc=BASE_URL,
        path='/'.join(pathitems) + '/',
        qs=('?' + urlencode(params)) if params else '')

def is_numeric(string):
    """Return true if string represents an integer, else false"""
    try:
        int(string)
    except ValueError:
        return False
    return True

def get_local_string(string_id):
    """Retrieve a localized string by its id"""
    src = xbmc if string_id < 30000 else ADDON
    return src.getLocalizedString(string_id)

def inject_video_id(path_offset, pathitems_arg='pathitems',
                    inject_remaining_pathitems=False):
    """Decorator that converts a pathitems argument into a VideoId
    and injects this into the decorated function instead. Pathitems
    that are to be converted into a video id must be passed into
    the function via kwarg defined by pathitems_arg (default=pathitems)"""
    # pylint: disable=missing-docstring
    def injecting_decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                kwargs['videoid'] = VideoId.from_path(
                    kwargs[pathitems_arg][path_offset:])
                if inject_remaining_pathitems:
                    kwargs[pathitems_arg] = kwargs[pathitems_arg][:path_offset]
                else:
                    del kwargs[pathitems_arg]
            except KeyError:
                raise Exception('Pathitems must be passed as kwarg {}'
                                .format(pathitems_arg))
            return func(*args, **kwargs)
        return wrapper
    return injecting_decorator

def refresh_container():
    xbmc.executebuiltin('Container.Refresh')
