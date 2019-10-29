import sys

#define >= 3 values here
itername = 'items'
string_encoding = 'unicode'
compat_unicode = str
compat_basestring = str

if (sys.version_info < (3, 0)):
    itername = 'iteritems'
    string_encoding = 'utf-8'
    compat_unicode = unicode
    compat_basestring = basestring
