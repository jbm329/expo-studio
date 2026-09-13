
# hooks/rthook_tqdm_disable.py
import os
# Stäng av tqdm globalt i GUI-bygget (gäller alla libs som använder tqdm).
os.environ.setdefault("TQDM_DISABLE", "1")
