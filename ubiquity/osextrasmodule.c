/* This is backported from Python 2.7. */

#include <Python.h>

#include "config.h"
#include <unistd.h>

PyDoc_STRVAR(osextras__doc__,
"This module adds a few functions which should really be in os, but aren't.");

#ifdef HAVE_SETRESUID
PyDoc_STRVAR(osextras_setresuid__doc__,
"setresuid(ruid, euid, suid)\n\n\
Set the current process's real, effective, and saved user ids.");

static PyObject*
osextras_setresuid (PyObject *self, PyObject *args)
{
	/* We assume uid_t is no larger than a long. */
	long ruid, euid, suid;
	if (!PyArg_ParseTuple(args, "lll", &ruid, &euid, &suid))
		return NULL;
	if (setresuid(ruid, euid, suid) < 0)
		return PyErr_SetFromErrno(PyExc_OSError);
	Py_RETURN_NONE;
}
#endif

#ifdef HAVE_SETRESGID
PyDoc_STRVAR(osextras_setresgid__doc__,
"setresgid(rgid, egid, sgid)\n\n\
Set the current process's real, effective, and saved group ids.");

static PyObject*
osextras_setresgid (PyObject *self, PyObject *args)
{
	/* We assume gid_t is no larger than a long. */
	long rgid, egid, sgid;
	if (!PyArg_ParseTuple(args, "lll", &rgid, &egid, &sgid))
		return NULL;
	if (setresgid(rgid, egid, sgid) < 0)
		return PyErr_SetFromErrno(PyExc_OSError);
	Py_RETURN_NONE;
}
#endif

#ifdef HAVE_GETRESUID
PyDoc_STRVAR(osextras_getresuid__doc__,
"getresuid() -> (ruid, euid, suid)\n\n\
Get tuple of the current process's real, effective, and saved user ids.");

static PyObject*
osextras_getresuid (PyObject *self, PyObject *args)
{
	uid_t ruid, euid, suid;
	long l_ruid, l_euid, l_suid;
	if (getresuid(&ruid, &euid, &suid) < 0)
		return PyErr_SetFromErrno(PyExc_OSError);
	/* Force the values into longs as we don't know the size of uid_t. */
	l_ruid = ruid;
	l_euid = euid;
	l_suid = suid;
	return Py_BuildValue("(lll)", l_ruid, l_euid, l_suid);
}
#endif

#ifdef HAVE_GETRESGID
PyDoc_STRVAR(osextras_getresgid__doc__,
"getresgid() -> (rgid, egid, sgid)\n\n\
Get tuple of the current process's real, effective, and saved group ids.");

static PyObject*
osextras_getresgid (PyObject *self, PyObject *args)
{
	gid_t rgid, egid, sgid;
	long l_rgid, l_egid, l_sgid;
	if (getresgid(&rgid, &egid, &sgid) < 0)
		return PyErr_SetFromErrno(PyExc_OSError);
	/* Force the values into longs as we don't know the size of gid_t. */
	l_rgid = rgid;
	l_egid = egid;
	l_sgid = sgid;
	return Py_BuildValue("(lll)", l_rgid, l_egid, l_sgid);
}
#endif

static PyMethodDef osextras_methods[] = {
#ifdef HAVE_SETRESUID
	{"setresuid", osextras_setresuid, METH_VARARGS,
	 osextras_setresuid__doc__},
#endif
#ifdef HAVE_SETRESGID
	{"setresgid", osextras_setresgid, METH_VARARGS,
	 osextras_setresgid__doc__},
#endif
#ifdef HAVE_GETRESUID
	{"getresuid", osextras_getresuid, METH_VARARGS,
	 osextras_getresuid__doc__},
#endif
#ifdef HAVE_GETRESGID
	{"getresgid", osextras_getresgid, METH_VARARGS,
	 osextras_getresgid__doc__},
#endif
	{NULL, NULL}
};

PyMODINIT_FUNC
init_osextras(void)
{
	PyObject *m;

	m = Py_InitModule3("_osextras", osextras_methods, osextras__doc__);
	if (m == NULL)
		return;
}
