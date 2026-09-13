# hooks/rthook_disable_typeguard.py
# Körs innan applikationskoden importeras.
import os

# Stäng av typeguard-instrumentering i produktion.
# TYPEGUARD_DISABLE stöds i typeguard ≥ 4.4.4.post11 (2024-11+) och senare.
os.environ.setdefault("TYPEGUARD_DISABLE", "1")

# Säkerhetsbälte: se också till att import-hooken inte aktiveras
# även om något skulle försöka install_import_hook().
os.environ.setdefault("TYPEGUARD_IMPORTHOOK", "0")
