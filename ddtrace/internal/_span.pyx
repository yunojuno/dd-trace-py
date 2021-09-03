from cpython cimport *
from cython.operator import dereference
from libc.string cimport strlen, strcpy
from libcpp.map cimport map

from cymem.cymem cimport Pool

from ..constants import MANUAL_DROP_KEY
from ..constants import MANUAL_KEEP_KEY
from ..constants import NUMERIC_TAGS
from ..constants import SERVICE_KEY
from ..constants import SERVICE_VERSION_KEY
from ..constants import SPAN_MEASURED_KEY
from ..constants import VERSION_KEY
from ..ext import http

cdef enum MetaType:
    NIL = 1
    STRING = 2
    LONG = 3

cdef struct MetaValue:
    MetaType type
    char* string_value
    long long long_value

cdef inline MetaValue* new_meta_value(Pool mem):
    return <MetaValue*> mem.alloc(1, sizeof(MetaValue))

ctypedef map[char*, MetaValue*] MetaData

cdef inline char* mem_str_copy(Pool mem, char* src):
    cdef char* dest = <char*> mem.alloc(strlen(src), sizeof(char))
    return strcpy(dest, src)


cdef class Meta:
    cdef MetaData data
    cdef Pool mem

    def __init__(self):
        self.mem = Pool()

    cpdef del_tag(self, object key):
        cdef char* c_key = <char*> key
        cdef MetaValue* value = self.data[c_key]
        if value != NULL:
            value.type = MetaType.NIL
            if value.string_value != NULL:
                self.mem.free(value.string_value)

    cpdef set_tag(self, object key, object py_value):
        cdef char* c_key = <char*> key
        cdef char* c_value = <char*> py_value
        cdef MetaValue* value = self.data[c_key]
        if value == NULL:
            value = new_meta_value(self.mem)
            self.data[c_key] = value

        value.type = MetaType.STRING
        value.string_value = mem_str_copy(self.mem, c_value)

    cpdef get_tag(self, object key):
        cdef char* c_key = <char*> key
        cdef MetaValue* value = self.data[c_key]
        if value is NULL:
            return None

        if value.type == MetaType.NIL:
            return None
        elif value.type == MetaType.LONG:
            return None
        else:
            return value.string_value

    cpdef set_metric(self, object key, object py_value):
        cdef char* c_key = <char*> key
        cdef long long c_value = <long long> py_value
        cdef MetaValue* value = self.data[c_key]
        if value == NULL:
            value = new_meta_value(self.mem)
            self.data[c_key] = value

        if value.type == MetaType.STRING:
            self.mem.free(value.string_value)

        value.type = MetaType.LONG
        value.long_value = c_value

    cpdef get_metric(self, object key):
        cdef char* c_key = <char*> key
        cdef MetaValue* value = self.data[c_key]
        if value is NULL:
            return None

        if value.type == MetaType.NIL:
            return None
        elif value.type == MetaType.LONG:
            return value.long_value
        else:
            return None


cdef class Span:
    cdef Meta meta

    def __cinit__(self):
        self.meta = Meta()

    cpdef set_tag(self, object key, object value):
        # type: (_TagNameType, Any) -> None
        """Set a tag key/value pair on the span.

        Keys must be strings, values must be ``stringify``-able.

        :param key: Key to use for the tag
        :type key: str
        :param value: Value to assign for the tag
        :type value: ``stringify``-able value
        """

        if not isinstance(key, six.string_types):
            log.warning("Ignoring tag pair %s:%s. Key must be a string.", key, value)
            return

        # Special case, force `http.status_code` as a string
        # DEV: `http.status_code` *has* to be in `meta` for metrics
        #   calculated in the trace agent
        if key == http.STATUS_CODE:
            value = str(value)

        # Determine once up front
        val_is_an_int = is_integer(value)

        # Explicitly try to convert expected integers to `int`
        # DEV: Some integrations parse these values from strings, but don't call `int(value)` themselves
        INT_TYPES = (net.TARGET_PORT, )
        if key in INT_TYPES and not val_is_an_int:
            try:
                value = int(value)
                val_is_an_int = True
            except (ValueError, TypeError):
                pass

        # Set integers that are less than equal to 2^53 as metrics
        if value is not None and val_is_an_int and abs(value) <= 2 ** 53:
            self.set_metric(key, value)
            return

        # All floats should be set as a metric
        elif PyLong_Check(value):
            self.set_metric(key, value)
            return

        # Key should explicitly be converted to a float if needed
        elif key in NUMERIC_TAGS:
            if value is None:
                log.debug("ignoring not number metric %s:%s", key, value)
                return

            try:
                # DEV: `set_metric` will try to cast to `float()` for us
                self.set_metric(key, value)
            except (TypeError, ValueError):
                log.warning("error setting numeric metric %s:%s", key, value)

            return

        elif key == MANUAL_KEEP_KEY:
            self.context.sampling_priority = priority.USER_KEEP
            return
        elif key == MANUAL_DROP_KEY:
            self.context.sampling_priority = priority.USER_REJECT
            return
        elif key == SERVICE_KEY:
            self.service = value
        elif key == SERVICE_VERSION_KEY:
            # Also set the `version` tag to the same value
            # DEV: Note that we do no return, we want to set both
            self.meta.set_tag(VERSION_KEY, value)
        elif key == SPAN_MEASURED_KEY:
            # Set `_dd.measured` tag as a metric
            # DEV: `set_metric` will ensure it is an integer 0 or 1
            if value is None:
                value = 1
            self.meta.set_metric(key, value)
            return

        try:
            self.meta.set_tag(key, value)
        except Exception:
            log.warning("error setting tag %s, ignoring it", key, exc_info=True)
