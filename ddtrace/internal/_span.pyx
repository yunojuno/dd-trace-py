from cpython cimport *
from libc.stdlib cimport free
from ._utils cimport PyObject_Copy_Str


cdef inline void _free_str(char* c_str):
    if c_str != NULL:
        free(c_str)

cdef inline unicode tounicode(const char* s):
    return s.decode('UTF-8', 'strict')


cdef class Span:
    def __dealloc__(self):
        _free_str(self._name)
        _free_str(self._service)
        _free_str(self._resource)

    @property
    def name(self):
        if self._name == NULL:
            return None
        return tounicode(self._name)

    @name.setter
    def name(self, object value):
        if value is None:
            _free_str(self._name)
            self._name = NULL
        else:
            self._name = PyObject_Copy_Str(value)

    @property
    def service(self):
        if self._service == NULL:
            return None
        return tounicode(self._service)

    @service.setter
    def service(self, object value):
        if value is None:
            _free_str(self._service)
            self._service = NULL
        else:
            self._service = PyObject_Copy_Str(value)

    @property
    def resource(self):
        if self._resource == NULL:
            return None
        return tounicode(self._resource)

    @resource.setter
    def resource(self, object value):
        if value is None:
            _free_str(self._resource)
            self._resource = NULL
        else:
            self._resource = PyObject_Copy_Str(value)
