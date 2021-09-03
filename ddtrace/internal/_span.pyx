from cpython cimport *
from libc.stdlib cimport free
from ._utils cimport PyObject_Copy_Str


cdef inline void _free_str(char* c_str):
    if c_str != NULL:
        free(c_str)

cdef class Span:
    def __dealloc__(self):
        _free_str(self._name)

    @property
    def name(self):
        if self._name == NULL:
            return None
        return self._name

    @name.setter
    def name(self, object value):
        if value is None:
            _free_str(self._name)
            self._name = NULL
        else:
            self._name = PyObject_Copy_Str(value)
