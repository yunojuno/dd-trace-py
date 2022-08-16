from libc.stdint cimport uint8_t, uintptr_t
from libcpp cimport bool

cdef extern from *:

  cdef enum ddog_LogLevel:
    DDOG_LOG_LEVEL_ERROR,
    DDOG_LOG_LEVEL_WARN,
    DDOG_LOG_LEVEL_DEBUG,

  cdef enum ddog_TelemetryWorkerBuilderProperty:
    DDOG_TELEMETRY_WORKER_BUILDER_PROPERTY_APPLICATION_SERVICE_VERSION,
    DDOG_TELEMETRY_WORKER_BUILDER_PROPERTY_APPLICATION_ENV,
    DDOG_TELEMETRY_WORKER_BUILDER_PROPERTY_APPLICATION_RUNTIME_NAME,
    DDOG_TELEMETRY_WORKER_BUILDER_PROPERTY_APPLICATION_RUNTIME_VERSION,
    DDOG_TELEMETRY_WORKER_BUILDER_PROPERTY_APPLICATION_RUNTIME_PATCHES,
    DDOG_TELEMETRY_WORKER_BUILDER_PROPERTY_HOST_CONTAINER_ID,
    DDOG_TELEMETRY_WORKER_BUILDER_PROPERTY_HOST_OS,
    DDOG_TELEMETRY_WORKER_BUILDER_PROPERTY_HOST_KERNEL_NAME,
    DDOG_TELEMETRY_WORKER_BUILDER_PROPERTY_HOST_KERNEL_RELEASE,
    DDOG_TELEMETRY_WORKER_BUILDER_PROPERTY_HOST_KERNEL_VERSION,
    DDOG_TELEMETRY_WORKER_BUILDER_PROPERTY_RUNTIME_ID,

  cdef struct ddog_TelemetryWorkerBuilder:
    pass

  cdef struct ddog_TelemetryWorkerHandle:
    pass

  # Holds the raw parts of a Rust Vec; it should only be created from Rust,
  # never from C.
  # The names ptr and len were chosen to minimize conversion from a previous
  # Buffer type which this has replaced to become more general.
  cdef struct ddog_Vec_u8:
    const uint8_t *ptr;
    uintptr_t len;
    uintptr_t capacity;

  cdef enum ddog_Option_vec_u8_Tag:
    DDOG_OPTION_VEC_U8_SOME_VEC_U8,
    DDOG_OPTION_VEC_U8_NONE_VEC_U8,

  cdef struct ddog_Option_vec_u8:
    ddog_Option_vec_u8_Tag tag;
    ddog_Vec_u8 some;

  ctypedef ddog_Option_vec_u8 ddog_MaybeError;

  # Remember, the data inside of each member is potentially coming from FFI,
  # so every operation on it is unsafe!
  cdef struct ddog_Slice_c_char:
    const char *ptr;
    uintptr_t len;

  ctypedef ddog_Slice_c_char ddog_CharSlice;

  cdef enum ddog_Option_bool_Tag:
    DDOG_OPTION_BOOL_SOME_BOOL,
    DDOG_OPTION_BOOL_NONE_BOOL,

  cdef struct ddog_Option_bool:
    ddog_Option_bool_Tag tag;
    bool some;

  ddog_MaybeError dd_shared_builder_instantiate(ddog_TelemetryWorkerBuilder **builder,
                                                ddog_CharSlice service_name,
                                                ddog_CharSlice language_name,
                                                ddog_CharSlice language_version,
                                                ddog_CharSlice tracer_version);

  ddog_MaybeError dd_shared_builder_instantiate_with_hostname(ddog_TelemetryWorkerBuilder **builder,
                                                              ddog_CharSlice hostname,
                                                              ddog_CharSlice service_name,
                                                              ddog_CharSlice language_name,
                                                              ddog_CharSlice language_version,
                                                              ddog_CharSlice tracer_version);

  ddog_MaybeError dd_shared_builder_with_application_service_version(ddog_TelemetryWorkerBuilder *builder,
                                                                     ddog_CharSlice param);

  ddog_MaybeError dd_shared_builder_with_application_env(ddog_TelemetryWorkerBuilder *builder,
                                                         ddog_CharSlice param);

  ddog_MaybeError dd_shared_builder_with_application_runtime_name(ddog_TelemetryWorkerBuilder *builder,
                                                                  ddog_CharSlice param);

  ddog_MaybeError dd_shared_builder_with_application_runtime_version(ddog_TelemetryWorkerBuilder *builder,
                                                                     ddog_CharSlice param);

  ddog_MaybeError dd_shared_builder_with_application_runtime_patches(ddog_TelemetryWorkerBuilder *builder,
                                                                     ddog_CharSlice param);

  ddog_MaybeError dd_shared_builder_with_host_container_id(ddog_TelemetryWorkerBuilder *builder,
                                                           ddog_CharSlice param);

  ddog_MaybeError dd_shared_builder_with_host_os(ddog_TelemetryWorkerBuilder *builder,
                                                 ddog_CharSlice param);

  ddog_MaybeError dd_shared_builder_with_host_kernel_name(ddog_TelemetryWorkerBuilder *builder,
                                                          ddog_CharSlice param);

  ddog_MaybeError dd_shared_builder_with_host_kernel_release(ddog_TelemetryWorkerBuilder *builder,
                                                             ddog_CharSlice param);

  ddog_MaybeError dd_shared_builder_with_host_kernel_version(ddog_TelemetryWorkerBuilder *builder,
                                                             ddog_CharSlice param);

  ddog_MaybeError dd_shared_builder_with_runtime_id(ddog_TelemetryWorkerBuilder *builder,
                                                    ddog_CharSlice param);

  # Sets a property from it's string value.
  #
  # # Available properties:
  #
  # * application.service_version
  #
  # * application.env
  #
  # * application.runtime_name
  #
  # * application.runtime_version
  #
  # * application.runtime_patches
  #
  # * host.container_id
  #
  # * host.os
  #
  # * host.kernel_name
  #
  # * host.kernel_release
  #
  # * host.kernel_version
  #
  # * runtime_id
  #
  #
  ddog_MaybeError dd_shared_builder_with_property(ddog_TelemetryWorkerBuilder *builder,
                                                  ddog_TelemetryWorkerBuilderProperty property,
                                                  ddog_CharSlice param);

  # Sets a property from it's string value.
  #
  # # Available properties:
  #
  # * application.service_version
  #
  # * application.env
  #
  # * application.runtime_name
  #
  # * application.runtime_version
  #
  # * application.runtime_patches
  #
  # * host.container_id
  #
  # * host.os
  #
  # * host.kernel_name
  #
  # * host.kernel_release
  #
  # * host.kernel_version
  #
  # * runtime_id
  #
  #
  ddog_MaybeError dd_shared_builder_with_str_property(ddog_TelemetryWorkerBuilder *builder,
                                                      ddog_CharSlice property,
                                                      ddog_CharSlice param);

  ddog_MaybeError dd_shared_builder_with_native_deps(ddog_TelemetryWorkerBuilder *builder,
                                                     bool include_native_deps);

  ddog_MaybeError dd_shared_builder_with_rust_shared_lib_deps(ddog_TelemetryWorkerBuilder *builder,
                                                              bool include_rust_shared_lib_deps);

  ddog_MaybeError dd_shared_builder_with_config(ddog_TelemetryWorkerBuilder *builder,
                                                ddog_CharSlice name,
                                                ddog_CharSlice value);

  ddog_MaybeError dd_shared_builder_run(ddog_TelemetryWorkerBuilder *builder,
                                        ddog_TelemetryWorkerHandle **handle);

  ddog_MaybeError dd_shared_handle_add_dependency(const ddog_TelemetryWorkerHandle *handle,
                                                  ddog_CharSlice dependency_name,
                                                  ddog_CharSlice dependency_version);

  ddog_MaybeError dd_shared_handle_add_integration(const ddog_TelemetryWorkerHandle *handle,
                                                   ddog_CharSlice dependency_name,
                                                   ddog_CharSlice dependency_version,
                                                   ddog_Option_bool compatible,
                                                   ddog_Option_bool enabled,
                                                   ddog_Option_bool auto_enabled);

  ddog_MaybeError dd_shared_handle_add_log(const ddog_TelemetryWorkerHandle *handle,
                                           ddog_CharSlice indentifier,
                                           ddog_CharSlice message,
                                           ddog_LogLevel level,
                                           ddog_CharSlice stack_trace);

  ddog_MaybeError dd_shared_handle_start(const ddog_TelemetryWorkerHandle *handle);

  ddog_TelemetryWorkerHandle *dd_shared_handle_clone(const ddog_TelemetryWorkerHandle *handle);

  ddog_MaybeError dd_shared_handle_stop(const ddog_TelemetryWorkerHandle *handle);

  void dd_shared_handle_wait_for_shutdown(ddog_TelemetryWorkerHandle *handle);

  void dd_shared_handle_drop(ddog_TelemetryWorkerHandle *handle);
