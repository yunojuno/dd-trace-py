from cpython cimport *
from cpython.bytearray cimport PyByteArray_Check
from cython.operator import dereference, postincrement
from libc.stdlib cimport free
from libc.string cimport strcpy, strlen
from ._c_utils cimport PyObject_Copy_Str


cdef class Span:

    @property
    def trace_id(self):
        return self.c_trace_id

    @trace_id.setter
    def trace_id(self, unsigned long long value):
        self.c_trace_id = value

    @property
    def span_id(self):
        return self.c_span_id

    @span_id.setter
    def span_id(self, unsigned long long value):
        self.c_span_id = value

    @property
    def parent_id(self):
        return self.c_parent_id

    @parent_id.setter
    def parent_id(self, object value):
        if value is None:
            self.c_parent_id = 0
        else:
            self.c_parent_id = value

    @property
    def service(self):
        if self.c_service == NULL:
            return None
        return self.c_service

    @service.setter
    def service(self, object value):
        self.c_service = PyObject_Copy_Str(value)

    @property
    def resource(self):
        if self.c_resource == NULL:
            return None
        return self.c_resource

    @resource.setter
    def resource(self, object value):
        self.c_resource = PyObject_Copy_Str(value)

    @property
    def name(self):
        if self.c_name == NULL:
            return None
        return self.c_name

    @name.setter
    def name(self, object value):
        if value is None:
            if self.c_name != NULL:
                free(self.c_name)
            self.c_name = NULL
        else:
            self.c_name = PyObject_Copy_Str(value)

    # TODO: Make this be `def span_type`
    @property
    def _span_type(self):
        if self.c_span_type == NULL:
            return None
        return self.c_span_type

    @_span_type.setter
    def _span_type(self, object value):
        cdef char* _type
        if value is None:
            if self.c_span_type != NULL:
                free(self.c_span_type)
            self.c_span_type = NULL
        else:
            self.c_span_type = PyObject_Copy_Str(value)

    @property
    def error(self):
        return <int> self.c_error

    @error.setter
    def error(self, object value):
        self.c_error = bool(value)

    @property
    def start_ns(self):
        return self.c_start_ns

    @start_ns.setter
    def start_ns(self, long value):
        self.c_start_ns = value

    @property
    def duration_ns(self):
        if self.c_duration_ns == 0:
            return None
        return self.c_duration_ns

    @duration_ns.setter
    def duration_ns(self, object value):
        if value is None:
            self.c_duration_ns = 0
        else:
            if value < 0:
                raise ValueError("Span duration cannot be less than 0 nanoseconds")
            self.c_duration_ns = value

    def set_tag(self, object key, object value):
        cdef char* c_key = PyObject_Copy_Str(key)

        # Setting the value as `None` will remove it
        if value is None:
            self.c_meta.erase(c_key)
        else:
            self.c_meta[c_key] = PyObject_Copy_Str(value)

    def get_tag(self, object key):
        cdef char* c_key = PyObject_Copy_Str(key)
        it = self.c_meta.find(c_key)
        while it != self.c_meta.end():
            return dereference(it).second
        return None

    def set_metric(self, object key, object value):
        cdef char* c_key = PyObject_Copy_Str(key)
        if value is None:
            self.c_metrics.erase(c_key)
        else:
            self.c_metrics[c_key] = <long long> value;

    def get_metric(self, object key):
        cdef char* c_key = PyObject_Copy_Str(key)
        cdef map[char*, long long].iterator it

        it = self.c_metrics.find(c_key)
        while it != self.c_metrics.end():
            return dereference(it).second
        return None

    @property
    def meta(self):
        return self.c_meta

    @property
    def metrics(self):
        return self.c_metrics
