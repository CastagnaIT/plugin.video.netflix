#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Module: utils
# Created on: 13.01.2017

# Takes everything, does nothing, classic no operation function
def noop (**kwargs):
    return True

# log decorator
def log(f, name=None):
    if name is None:
        name = f.func_name
    def wrapped(*args, **kwargs):
        that = args[0]
        class_name = that.__class__.__name__
        arguments = ''
        for key, value in kwargs.iteritems():
            if key != 'account' and key != 'credentials':
                arguments += ":%s = %s:" % (key, value)
        if arguments != '':
            that.log('"' + class_name + '::' + name + '" called with arguments ' + arguments)
        else:
            that.log('"' + class_name + '::' + name + '" called')
        result = f(*args, **kwargs)
        that.log('"' + class_name + '::' + name + '" returned: ' + str(result))
        return result
    wrapped.__doc__ = f.__doc__
    return wrapped
