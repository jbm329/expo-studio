# hooks/rthook_streams_null.py
import sys


class _NullWriter:
    def write(self, *_args, **_kwargs):
        pass

    def flush(self):
        pass


# I GUI/--windowed är strömmarna ofta None – ge dem no-op writers.
if getattr(sys, "stdout", None) is None:
    sys.stdout = _NullWriter()
if getattr(sys, "stderr", None) is None:
    sys.stderr = _NullWriter()

