from resources.lib.utils import log

class TestLoggerWithNoArgs(object):
    def __init__(self, logger_1):
        self.log = logger_1
    @log
    def to_be_logged(self):
        return None

class TestLoggerWithArgs(object):
    def __init__(self, logger_2):
        self.log = logger_2
    @log
    def to_be_logged(self, a):
        return None

class TestLoggerWithCredentialArgs(object):
    def __init__(self,logger_3):
        self.log = logger_3
    @log
    def to_be_logged(self, credentials, account, a):
        return None
