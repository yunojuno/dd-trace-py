#include <string.h>

static inline int PyBytesLike_Check(PyObject* o) {
  return PyBytes_Check(o) || PyByteArray_Check(o);
}

static inline char* PyObject_Copy_Str(PyObject* o) {
  PyObject* temp;
  char* borrowed;

  if (PyBytesLike_Check(o)) {
    borrowed = PyBytes_AS_STRING(o);
    borrowed = strdup(borrowed);
  } else if (PyUnicode_Check(o)) {
    temp = PyUnicode_AsEncodedString(o, "utf-8", NULL);
    if (temp == NULL) {
      return NULL;
    }
    borrowed = PyBytes_AS_STRING(temp);
    borrowed = strdup(borrowed);
    Py_DECREF(temp);
  } else {
    temp = PyObject_Str(o);
    if (temp == NULL) {
      return NULL;
    }

    borrowed = PyBytes_AS_STRING(temp);
    borrowed = strdup(borrowed);
    Py_DECREF(temp);
  }

  return borrowed;
}
