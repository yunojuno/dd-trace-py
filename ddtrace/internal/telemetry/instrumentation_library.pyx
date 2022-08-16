from ddtrace.internal.telemetry.instrumentation_library cimport *
from cpython.version cimport PY_MAJOR_VERSION
from cpython.bytearray cimport PyByteArray_Size

cdef class TelemetryBuilder:
    cdef ddog_TelemetryWorkerBuilder* builder

    def __init__(
        self,
        service_name,
        language_name,
        language_version,
        tracer_version,
        hostname=None
    ):
        self.builder = NULL
        if hostname is None:
            wrap_instrumentation_library_ffi_error(dd_shared_builder_instantiate(
                &self.builder,
                _encode(service_name),
                _encode(language_name),
                _encode(language_version),
                _encode(tracer_version),
            ))
        else:
            wrap_instrumentation_library_ffi_error(dd_shared_builder_instantiate_with_hostname(
                &self.builder,
                _encode(hostname),
                _encode(service_name),
                _encode(language_name),
                _encode(language_version),
                _encode(tracer_version),
            ))        
    
    def assert_builder_not_already_used(self):
        if self.builder == NULL:
            raise Exception("This builder has already been used")
    
    def with_optional_property(self, property, value):
        self.assert_builder_not_already_used()
        wrap_instrumentation_library_ffi_error(
            dd_shared_builder_with_str_property(
                self.builder,
                _encode(property),
                _encode(value)
            )
        )
        return self
    
    def with_config(self, name, value):
        self.assert_builder_not_already_used()
        wrap_instrumentation_library_ffi_error(
            dd_shared_builder_with_config(
                self.builder,
                _encode(name),
                _encode(value)
            )
        )
        return self
    
    def with_rust_shared_lib_deps(self, enable):
        self.assert_builder_not_already_used()
        wrap_instrumentation_library_ffi_error(
            dd_shared_builder_with_rust_shared_lib_deps(
                self.builder,
                enable
            )
        )
        return self
    
    def with_native_deps(self, enable):
        self.assert_builder_not_already_used()
        wrap_instrumentation_library_ffi_error(
            dd_shared_builder_with_native_deps(
                self.builder,
                enable
            )
        )
        return self
    
    def build(self):
        self.assert_builder_not_already_used()
        return Telemetry(self)
        

cdef class Telemetry:
    cdef ddog_TelemetryWorkerHandle* handle
    def __init__(self, TelemetryBuilder builder):
        dd_shared_builder_run(builder.builder, &self.handle)
        builder.builder = NULL
    
    def __del__(self):
        wrap_instrumentation_library_ffi_error(dd_shared_handle_drop(self.handle))
    
    def add_dependency(self, name, version=None):
        cdef ddog_CharSlice utf8_version
        if version is not None:
            utf8_version = _encode(version)

        wrap_instrumentation_library_ffi_error(dd_shared_handle_add_dependency(
            self.handle,
            _encode(name),
            utf8_version,
        ))

    def log(self, indentifier, message, level="DEBUG", stack_trace=None):
        cdef ddog_LogLevel c_level
        if level == "ERROR":
            c_level = ddog_LogLevel.DDOG_LOG_LEVEL_ERROR
        elif level == "WARN":
            c_level = ddog_LogLevel.DDOG_LOG_LEVEL_WARN
        else:
            c_level = ddog_LogLevel.DDOG_LOG_LEVEL_DEBUG
        cdef ddog_CharSlice utf8_stack_trace
        if stack_trace is not None:
            utf8_stack_trace = _encode(stack_trace)
        wrap_instrumentation_library_ffi_error(dd_shared_handle_add_log(
            self.handle,
            _encode(indentifier),
            _encode(message),
            c_level,
            utf8_stack_trace,
        ))

    def start(self):
        wrap_instrumentation_library_ffi_error(dd_shared_handle_start(self.handle))
    
    def stop(self):
        wrap_instrumentation_library_ffi_error(dd_shared_handle_stop(self.handle))

    def wait_for_shutdown(self):
        dd_shared_handle_wait_for_shutdown(self.handle)

def wrap_instrumentation_library_ffi_error(ret):
    if ret < 0:
        raise Exception("Telemetry went kaboom with code {}".format(-ret))

cdef bytes _encode(data):
    if isinstance(data, (bytes, bytearray)):
        k = data
    elif PY_MAJOR_VERSION < 3: 
        k = data.encode('utf8')
    else:
        k = data.encode()

    cdef ddog_CharSlice charSlice
    charSlice.ptr = k
    charSlice.len = len(k)
    return charSlice

# cdef _decode(char* c_string):
#     cdef bytes py_string
#     rv = None
#     if not c_string:
#         return rv
#     try:
#         py_string = c_string
#         rv = py_string.decode('utf8')
#     finally:
#         pass
#         # dd_shared_string_free(c_string)
#     return rv

# def dd_get_container_id():
#     return _decode(dd_shared_get_container_id())
    
# def dd_get_host_data_json():
#     return _decode(dd_shared_get_host_data_json())
    
# def dd_poc_string_len_mirror(data):
#     cdef bytes encoded = _encode(data)
#     cdef Py_ssize_t l = len(encoded)
#     return _decode(dd_shared_poc_string_len_mirror(encoded, l))

# def dd_poc_string_mirror(data):
#     cdef bytes encoded = _encode(data)
#     return _decode(dd_shared_poc_string_mirror(encoded))

# def dd_bmark_string_len_inferred(data):
#     cdef bytes encoded = _encode(data)
#     return dd_shared_bmark_string_len_inferred(encoded)

# def dd_bmark_string_len_passed(data):
#     cdef bytes encoded = _encode(data)
#     cdef Py_ssize_t l = PyByteArray_Size(encoded)
#     return dd_shared_bmark_string_len_passed(encoded, l)
