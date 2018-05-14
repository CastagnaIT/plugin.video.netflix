import base64
from Cryptodome import Random
from Cryptodome.Cipher import AES
from Cryptodome.Util import Padding
from utils import uniq_id

class NetflixCredentials(object):
    """
    Stuff shared between / used from service and addon"""

    def __init__(self):
        self.bs = 32
        self.crypt_key = uniq_id()

    def encode_credentials(self, email, password):
        """Returns the users stored credentials

        Returns
        -------
        :obj:`dict` of :obj:`str`
            The users stored account data
        """
        # if everything is fine, we encode the values
        if '' != email or '' != password:
            return {
                'email': self.encode(raw=email),
                'password': self.encode(raw=password)
            }

        # if email is empty, we return an empty map
        return {
            'email': '',
            'password': ''
        }

    def decode_credentials(self, email, password):
        """Returns the users stored credentials

        Returns
        -------
        :obj:`dict` of :obj:`str`
            The users stored account data
        """
        # if everything is fine, we decode the values
        if (email and '' != email) or (password and '' != password):
            return {
                'email': self.decode(enc=email),
                'password': self.decode(enc=password)
            }

        # if email is empty, we return an empty map
        return {
            'email': '',
            'password': ''
        }

    def encode(self, raw):
        """
        Encodes data

        :param data: Data to be encoded
        :type data: str
        :returns:  string -- Encoded data
        """
        raw = bytes(Padding.pad(data_to_pad=raw, block_size=self.bs))
        iv = Random.new().read(AES.block_size)
        cipher = AES.new(self.crypt_key, AES.MODE_CBC, iv)
        return base64.b64encode(iv + cipher.encrypt(raw))

    def decode(self, enc):
        """
        Decodes data

        :param data: Data to be decoded
        :type data: str
        :returns:  string -- Decoded data
        """
        enc = base64.b64decode(enc)
        iv = enc[:AES.block_size]
        cipher = AES.new(self.crypt_key, AES.MODE_CBC, iv)
        decoded = Padding.unpad(
            padded_data=cipher.decrypt(enc[AES.block_size:]),
            block_size=self.bs).decode('utf-8')
        return decoded
