import xbmc
from xbmcaddon import Addon
import xbmcvfs
import json

from resources.lib.storage import PersistentStorage


class Signals(object):
    PLAYBACK_INITIATED = 'playback_initiated'


class NetflixCommon(object):
    """
    Stuff shared between / used from service and addon"""

    def __init__(self, plugin_handle, base_url):

        self.addon = Addon()
        self.data_path = xbmc.translatePath(self.addon.getAddonInfo('profile'))
        self.cookie_path = self.data_path + 'COOKIE'
        self.plugin = self.addon.getAddonInfo('name')
        self.verb_log = self.addon.getSetting('logging') == 'true'
        self.plugin_handle = plugin_handle
        self.base_url = base_url
        self.version = self.addon.getAddonInfo('version')

        xbmcvfs.mkdir(path=self.data_path)

    def get_addon(self):
        """Return the current addon instance"""
        return self.addon

    def get_addon_info(self, name):
        """Return the current addon instance"""
        return self.addon.getAddonInfo(name)

    def set_setting(self, key, value):
        return self.addon.setSetting(key, value)

    def get_setting(self, key):
        return self.addon.getSetting(key)

    def flush_settings(self):
        self.addon = Addon()

    def get_storage(self, storage_id):
        return PersistentStorage(storage_id, self)

    def get_esn(self):
        """
        Returns the esn from settings
        """
        return self.addon.getSetting('esn')

    def set_esn(self, esn):
        """
        Returns True if MSL reset is required
        """
        stored_esn = self.get_esn()
        if not stored_esn and esn:
            self.set_setting('esn', esn)
            return True
        return False

    def get_credentials(self):
        from NetflixCredentials import NetflixCredentials
        email = self.get_setting('email')
        password = self.get_setting('password')

        if '@' in email:
            self.set_credentials(email, password)
            return {'email' : email, 'password' : password }

        return NetflixCredentials().decode_credentials(email, password)

    def set_credentials(self, email, password):
        from NetflixCredentials import NetflixCredentials
        encoded = NetflixCredentials().encode_credentials(email, password)
        self.set_setting('email',encoded['email'])
        self.set_setting('password',encoded['password'])

    def log(self, msg, level=xbmc.LOGDEBUG):
        """Adds a log entry to the Kodi log

        Parameters
        ----------
        msg : :obj:`str`
            Entry that should be turned into a list item

        level : :obj:`int`
            Kodi log level
        """
        if isinstance(msg, unicode):
            msg = msg.encode('utf-8')
        xbmc.log('[%s] %s' % (self.plugin, msg.__str__()), level)

    @staticmethod
    def check_folder_path(path):
        """
        Check if folderpath ends with path delimator
        If not correct it (makes sure xbmcvfs.exists is working correct)
        """
        if isinstance(path, unicode):
            check = path.encode('ascii', 'ignore')
            if '/' in check and not str(check).endswith('/'):
                end = u'/'
                path = path + end
                return path
            if '\\' in check and not str(check).endswith('\\'):
                end = u'\\'
                path = path + end
                return path
        if '/' in path and not str(path).endswith('/'):
            path = path + '/'
            return path
        if '\\' in path and not str(path).endswith('\\'):
            path = path + '\\'
            return path

    @staticmethod
    def file_exists(data_path, filename):
        """
        Checks if a given file exists
        :param filename: The filename
        :return: True if so
        """
        return xbmcvfs.exists(path=data_path + filename)

    @staticmethod
    def save_file(data_path, filename, content):
        """
        Saves the given content under given filename
        :param filename: The filename
        :param content: The content of the file
        """

        file_handle = xbmcvfs.File(
            filepath=data_path + filename,
            mode='w')
        file_content = file_handle.write(content)
        file_handle.close()

    @staticmethod
    def load_file(data_path, filename):
        """
        Loads the content of a given filename
        :param filename: The file to load
        :return: The content of the file
        """
        file_handle = xbmcvfs.File(
            filepath=data_path + filename)
        file_content = file_handle.read()
        file_handle.close()
        return file_content

    @staticmethod
    def list_dir(data_path):
        return xbmcvfs.listdir(data_path)

    @staticmethod
    def compare_versions(v1, v2):
        if len(v1) != len(v2):
            return len(v1) - len(v2)
        for i in range(0, len(v1)):
            if v1[i] > v2[i]:
                return 1
            elif v1[i] < v2[i]:
                return -1
        return 0
