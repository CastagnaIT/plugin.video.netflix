class MockClass(object):
    def __init__(self):
        pass
    def foo():
        pass
    def bar():
        pass

class Error_resp_401(object):
    status_code = 401
    pass

class Error_resp_500(object):
    status_code = 500
    pass

class Success_resp(object):
    status_code = 200
    def json(self):
        return {'foo': 'bar'}
