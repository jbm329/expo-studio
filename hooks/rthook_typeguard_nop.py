# hooks/rthook_typeguard_nop.py
"""
Neutralisera typeguard.@typechecked innan ydata_profiling importeras.
Stöd både @typechecked och @typechecked(...).
"""
import os
os.environ.setdefault("TYPEGUARD_DISABLE", "1")     # extra skydd om versionen stödjer detta
os.environ.setdefault("TYPEGUARD_IMPORTHOOK", "0")  # säkerställ att import-hook ej används

try:
    import typeguard  # noqa
except (AttributeError, ConnectionError, FileNotFoundError, IndexError, KeyError, LookupError, OSError, RuntimeError, TypeError, ValueError):
    # typeguard kanske inte finns i miljön -> inget att göra
    pass
else:
    def _typechecked(target=None, *args, **kwargs):
        # Om dekoratorn används med parenteser (fabriksform), returnera en dekorator
        if target is None:
            def _decorator(obj):
                return obj
            return _decorator
        # Om dekoratorn används utan parenteser, returnera objektet oförändrat
        return target

    # Ersätt dekoratorn med vår no-op som hanterar båda fallen
    try:
        typeguard.typechecked = _typechecked  # type: ignore[attr-defined]
    except (AttributeError, ConnectionError, FileNotFoundError, IndexError, KeyError, LookupError, OSError, RuntimeError, TypeError, ValueError):
        pass