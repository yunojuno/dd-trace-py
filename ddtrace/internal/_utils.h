#include <string.h>

// Determine if the provided object can be treated as a `bytes`
static inline int PyBytesLike_Check(PyObject* o) {
  return PyBytes_Check(o) || PyByteArray_Check(o);
}

// Convert the provided `PyObject*` to a PyBytes and make a copy of it's `char*`
// DEV: We need to make a copy when we need to keep the `char*` around
//   longer than the scope of the owning `PyObject*`.
//
//   Consider:
//        cdef class NativeSpan:
//            cdef char* service
//
//            def set_service(self, object service):
//                self.service = <char*> service
//
//        span = NativeSpan()
//        span.set_service("service")
//
//   Unless we keep a reference to "service" (or do `Py_XINCREF`/`Py_XDECREF` manually)
//   then the `PyObject*` for "service" will get GC'd sometime after and the
//   `char*` we were using will no longer be valid.
static inline char* PyObject_Copy_Str(PyObject* o) {
  PyObject* temp;
  char* copied;

  if (PyBytesLike_Check(o)) {
    copied = strdup(PyBytes_AS_STRING(o));

  } else if (PyUnicode_Check(o)) {
#if (PY_MAJOR_VERSION == 3) && (PY_MINOR_VERSION >= 3)
    // Shortcut for >=3.3 to not need to convert to a bytes first
    copied = strdup(PyUnicode_AsUTF8(o));
#else
    // For Python 2 convert to a bytes first
    temp = PyUnicode_AsEncodedString(o, "utf-8", NULL);
    if (temp == NULL) {
      return NULL;
    }
    copied = strdup(PyBytes_AS_STRING(o));
    Py_DECREF(temp);
#endif

  } else {
    // Try to do `str(o)` on the `PyObject*` then re-call `PyObject_Copy_Str`
    // on that new `PyUnicode`
    temp = PyObject_Str(o);
    if (temp == NULL) {
      PyErr_Clear();
      return NULL;
    }
    copied = PyObject_Copy_Str(temp);
    Py_DECREF(temp);
  }

  return copied;
}
