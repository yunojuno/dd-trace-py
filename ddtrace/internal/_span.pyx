from cpython cimport *
from cpython.bytearray cimport PyByteArray_Check
from cython.operator import dereference
from libc.stdlib cimport malloc
from libc.string cimport strcpy, strlen


cdef char* object_to_cstr(object value):
    cdef char* c_value
    cdef Py_ssize_t n

    if value is None:
        return NULL
    elif PyBytes_Check(value) or PyByteArray_Check(value):
        return value
    elif PyUnicode_Check(value):
        n = len(value)
        c_value = <char*> malloc((n + 1) * sizeof(char))
        if not c_value:
            return NULL
        strcpy(c_value, value)
        return c_value
    else:
        value = str(value).encode("utf-8")

        n = len(value)
        c_value = <char*> malloc((n + 1) * sizeof(char))
        if not c_value:
            return NULL
        strcpy(c_value, value)
        return c_value

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
        cdef char* service
        service = object_to_cstr(value)
        print(service)
        self.c_service = service

    @property
    def resource(self):
        if self.c_resource == NULL:
            return None
        return self.c_resource

    @resource.setter
    def resource(self, object value):
        cdef char* resource
        resource = object_to_cstr(value)
        self.c_resource = resource

    @property
    def name(self):
        if self.c_name == NULL:
            return None
        return self.c_name

    @name.setter
    def name(self, object value):
        cdef char* name
        print(value)
        if value is None:
            self.c_name = NULL
        else:
            name = object_to_cstr(value)
            self.c_name = name

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
            self.c_span_type = NULL
        else:
            _type = object_to_cstr(value)
            self.c_span_type = _type

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
            self.c_duration_ns = value

    def set_tag(self, object key, object value):
        cdef char* c_key = object_to_cstr(key)

        # Setting the value as `None` will remove it
        if value is None:
            self.c_meta.erase(c_key)
        else:
            self.c_meta[c_key] = object_to_cstr(value)

    def get_tag(self, object key):
        cdef char* c_key = object_to_cstr(key)
        try:
            value = self.c_meta.at(c_key)
            if value != NULL:
                return value
        except IndexError:
            pass

        return None

    def set_metric(self, object key, object value):
        cdef char* c_key = object_to_cstr(key)
        if value is None:
            self.c_metrics.erase(c_key)
        else:
            self.c_metrics[c_key] = <long long> value;

    def get_metric(self, object key):
        cdef char* c_key = object_to_cstr(key)
        try:
            return self.c_metrics.at(c_key)
        except IndexError:
            return None

    @property
    def meta(self):
        return self.c_meta

    @property
    def metrics(self):
        return self.c_metrics
