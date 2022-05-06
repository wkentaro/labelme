"""
File: debugger.py
Author: Nrupatunga
Email: nrupatunga.tunga@gmail.com
Github: https://github.com/nrupatunga
Description: debugging utils
"""


def debug_trace():
    '''Set a tracepoint in the Python debugger that works with Qt'''
    from qtpy.QtCore import pyqtRemoveInputHook
    pyqtRemoveInputHook()
    __import__('pdb').set_trace()
