#include <string.h>

static inline int PyBytesLike_Check(PyObject* o) {
  return PyBytes_Check(o) || PyByteArray_Check(o);
}

static inline char* PyObject_Copy_Str(PyObject* o) {
  PyObject* temp;
  char* copied;

  if (PyBytesLike_Check(o)) {
    copied = PyBytes_AS_STRING(o);
    copied = strdup(copied);
  } else if (PyUnicode_Check(o)) {
    temp = PyUnicode_AsEncodedString(o, "utf-8", NULL);
    if (temp == NULL) {
      return NULL;
    }
    copied = PyBytes_AS_STRING(temp);
    copied = strdup(copied);
    Py_DECREF(temp);
  } else {
    temp = PyObject_Str(o);
    if (temp == NULL) {
      return NULL;
    }

    copied = PyBytes_AS_STRING(temp);
    copied = strdup(copied);
    Py_DECREF(temp);
  }

  return copied;
}
