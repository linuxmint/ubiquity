#include <pygobject.h>

void e_map_register_classes(PyObject *d);
extern PyMethodDef e_map_functions[];

DL_EXPORT(void)
initemap(void)
{
    PyObject *m, *d;

    init_pygobject();

    m = Py_InitModule("emap", e_map_functions);
    d = PyModule_GetDict(m);

    e_map_register_classes(d);

    if (PyErr_Occurred()) {
        Py_FatalError("can't initialise module emap");
    }
}
