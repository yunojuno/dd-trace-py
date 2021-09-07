from cpython cimport *
from cython.operator import dereference, postincrement
from libc.string cimport strlen, strcpy, strcmp
from libcpp.unordered_map cimport unordered_map

from cymem.cymem cimport Pool

from ._utils cimport PyBytesLike_Check

import contextlib
from ..constants import MANUAL_DROP_KEY
from ..constants import MANUAL_KEEP_KEY
from ..constants import NUMERIC_TAGS
from ..constants import SERVICE_KEY
from ..constants import SERVICE_VERSION_KEY
from ..constants import SPAN_MEASURED_KEY
from ..constants import VERSION_KEY
from ..ext import http

cdef enum TagType:
    NIL = 0
    STRING = 1
    LONG = 2

cdef struct TagValue:
    TagType type
    char* string_value
    long long long_value

ctypedef unordered_map[char*, TagValue*] TagData
ctypedef unordered_map[char*, TagValue*].iterator TagDataIterator

cdef inline char* mem_str_copy(Pool mem, char* src):
    cdef char* dest = <char*> mem.alloc(strlen(src), sizeof(char))
    return strcpy(dest, src)

cdef inline unicode tounicode(const char* s):
    return s.decode('UTF-8', 'strict')

@contextlib.contextmanager
def object_borrow_bytes(object value):
    cdef bytes b_temp
    cdef str s_temp

    if PyBytesLike_Check(value):
        yield value
    elif PyUnicode_Check(value):
        b_temp = PyUnicode_AsEncodedString(value, "utf-8", NULL)
        yield b_temp
    else:
        s_temp = PyObject_Str(value)
        b_temp = PyUnicode_AsEncodedString(s_temp, "utf-8", NULL)
        yield b_temp


cdef class TagMap:
    cdef TagData data
    cdef Pool mem

    def __init__(self):
        self.mem = Pool()

    cdef inline TagValue* new_tag(self, char* key):
        cdef char* key_copy = mem_str_copy(self.mem, key)
        cdef TagValue* value = <TagValue*> self.mem.alloc(1, sizeof(TagValue))
        value.type = TagType.NIL
        self.data[key_copy] = value
        return value

    cdef inline void _reset_value(self, TagValue* value):
        value.type = TagType.NIL
        if value.string_value != NULL:
            self.mem.free(value.string_value)

    cdef TagValue* get(self, char* key):
        return self.data[key]

    cdef void set_string(self, char* key, char* string_value):
        cdef TagValue* value = self.get(key)
        if value == NULL:
            value = self.new_tag(key)
        value.type = TagType.STRING
        value.string_value = mem_str_copy(self.mem, string_value)

    cdef TagValue* get_string(self, char* key):
        cdef TagValue* value = self.get(key)
        if value != NULL and value.type == TagType.STRING:
            return value
        return NULL

    cdef void set_long(self, char* key, long long long_value):
        cdef TagValue* value = self.get(key)
        if value == NULL:
            value = self.new_tag(key)

        if value.type == TagType.STRING:
            self._reset_value(value)

        value.type = TagType.LONG
        value.long_value = long_value

    cdef TagValue* get_long(self, char* key):
        cdef TagValue* value = self.get(key)
        if value != NULL and value.type == TagType.LONG:
            return value
        return NULL

    cdef void remove(self, char* key):
        cdef TagValue* value = self.get(key)
        if value != NULL:
            self._reset_value(value)
        self.data.erase(key)

    cdef TagDataIterator begin(self):
        return self.data.begin()

    cdef TagDataIterator end(self):
        return self.data.end()


cdef class ScopedTagsBase:
    cdef TagMap _tags
    cdef TagType tags_type

    def __init__(self, TagMap tags):
        self._tags = tags

    def __getitem__(self, str key):
        cdef TagValue* value = NULL
        cdef bytes k_temp
        with object_borrow_bytes(key) as k_temp:
            if self.tags_type == TagType.STRING:
                value = self._tags.get_string(k_temp)
                if value == NULL:
                    raise KeyError(key)
                return tounicode(value.string_value)
            elif self.tags_type == TagType.LONG:
                value = self._tags.get_long(k_temp)
                if value == NULL:
                    raise KeyError(key)
                return value.long_value

        return None

    def get(self, str key, object default = None):
        try:
            return self[key]
        except KeyError:
            return default

    def __delitem__(self, str key):
        cdef bytes k_temp = <bytes> key
        self._tags.remove(k_temp)

    def __setitem__(self, str key, object value):
        cdef bytes k_temp = <bytes> key
        cdef bytes v_temp
        if value is None:
            self._tags.remove(k_temp)

        if self.tags_type == TagType.STRING:
            v_temp = <bytes> value
            self._tags.set_string(k_temp, v_temp)
        elif self.tags_type == TagType.LONG:
            self._tags.set_long(k_temp, value)

    def __iter__(self):
        cdef TagDataIterator it = self._tags.begin()
        while it != self._tags.end():
            print(dereference(it).first)
            yield tounicode(dereference(it).first)
            postincrement(it)


cdef class Meta(ScopedTagsBase):
    def __init__(self, TagMap tags):
        self.tags_type = TagType.STRING
        super(Meta, self).__init__(tags)


cdef class Metrics(ScopedTagsBase):
    def __init__(self, TagMap tags):
        self.tags_type = TagType.LONG
        super(Metrics, self).__init__(tags)


cdef class Span:
    cdef TagMap _tags
    cdef readonly Meta meta
    cdef readonly Metrics metrics

    def __cinit__(self):
        self._tags = TagMap()
        self.meta = Meta(self._tags)
        self.metrics = Metrics(self._tags)
