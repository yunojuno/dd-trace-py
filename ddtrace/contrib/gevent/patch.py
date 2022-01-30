import gevent
import gevent.pool
import greenlet

import ddtrace

from ...internal.utils.formats import asbool
from ...internal.utils.formats import get_env
from ...provider import DefaultContextProvider
from .greenlet import GEVENT_VERSION
from .greenlet import TracedGreenlet
from .greenlet import TracedIMap
from .greenlet import TracedIMapUnordered
from .provider import GeventContextProvider


__Greenlet = gevent.Greenlet
__IMap = gevent.pool.IMap
__IMapUnordered = gevent.pool.IMapUnordered

ddtrace.config._add(
    "gevent",
    dict(
        trace_context_switches=asbool(get_env("gevent", "trace_context_switches", default=False)),
    ),
)


def patch():
    """
    Patch the gevent module so that all references to the
    internal ``Greenlet`` class points to the ``DatadogGreenlet``
    class.

    This action ensures that if a user extends the ``Greenlet``
    class, the ``TracedGreenlet`` is used as a parent class.
    """
    _replace(TracedGreenlet, TracedIMap, TracedIMapUnordered)
    ddtrace.tracer.configure(context_provider=GeventContextProvider())

    if ddtrace.config.gevent.trace_context_switches:
        _setup_tracing()


def unpatch():
    """
    Restore the original ``Greenlet``. This function must be invoked
    before executing application code, otherwise the ``DatadogGreenlet``
    class may be used during initialization.
    """
    _replace(__Greenlet, __IMap, __IMapUnordered)
    ddtrace.tracer.configure(context_provider=DefaultContextProvider())

    _tracing_func = greenlet.gettrace()
    if _tracing_func:
        if getattr(_tracing_func, "__original_func", None):
            greenlet.settrace(_tracing_func.__original_func)
        else:
            greenlet.settrace(None)


def _replace(g_class, imap_class, imap_unordered_class):
    """
    Utility function that replace the gevent Greenlet class with the given one.
    """
    # replace the original Greenlet classes with the new one
    gevent.greenlet.Greenlet = g_class

    if GEVENT_VERSION >= (1, 3):
        # For gevent >= 1.3.0, IMap and IMapUnordered were pulled out of
        # gevent.pool and into gevent._imap
        gevent._imap.IMap = imap_class
        gevent._imap.IMapUnordered = imap_unordered_class
        gevent.pool.IMap = gevent._imap.IMap
        gevent.pool.IMapUnordered = gevent._imap.IMapUnordered
        gevent.pool.Greenlet = gevent.greenlet.Greenlet
    else:
        # For gevent < 1.3, only patching of gevent.pool classes necessary
        gevent.pool.IMap = imap_class
        gevent.pool.IMapUnordered = imap_unordered_class

    gevent.pool.Group.greenlet_class = g_class

    # replace gevent shortcuts
    gevent.Greenlet = gevent.greenlet.Greenlet
    gevent.spawn = gevent.greenlet.Greenlet.spawn
    gevent.spawn_later = gevent.greenlet.Greenlet.spawn_later


def _setup_tracing():
    _original_func = greenlet.gettrace()

    def _tracing(event, args):
        try:
            if event in ("switch", "throw"):
                origin, target = args

                # Try to get any active spans in either the origin or target contexts
                ctx_origin = getattr(origin, GeventContextProvider._CONTEXT_ATTR, None)
                ctx_target = getattr(target, GeventContextProvider._CONTEXT_ATTR, None)

                # Context switching away from an active span
                if isinstance(ctx_origin, ddtrace.Span):
                    # Create a new span to represent this context switch
                    span = ddtrace.tracer.start_span(
                        "gevent.ctx_switch",
                        service="gevent",
                        child_of=ctx_origin,
                        activate=False,
                    )
                    # Set this span as the active span on the origin greenlet
                    setattr(origin, GeventContextProvider._CONTEXT_ATTR, span)

                # Context switching back to an active span
                if isinstance(ctx_target, ddtrace.Span):
                    # We are context switching back to a greenlet that
                    # we are tracing context switches from, finish the span
                    if ctx_target.name == "gevent.ctx_switch":
                        ctx_target.finish()
                        # Manually reactivate the parent span in the target greenlet
                        setattr(target, GeventContextProvider._CONTEXT_ATTR, ctx_target._parent)

        finally:
            if _original_func is not None:
                _original_func(event, args)

    setattr(_tracing, "__original_func", _original_func)
    greenlet.settrace(_tracing)
