import os
from pathlib import Path
from unittest.mock import patch

from expo_jbm329.utils.paths import expand


def test_expand_expands_home_and_env_vars():
    with patch.dict(os.environ, {"HOME": "/home/user", "USERPROFILE": "C:\\Users\\user"}):
        expanded = expand("~/test")
        assert "test" in str(expanded)

    with patch.dict(os.environ, {"MY_VAR": "my_val"}):
        expanded = expand("$MY_VAR/test")
        assert "my_val" in str(expanded)
        assert "test" in str(expanded)


def test_expand_accepts_path_objects():
    path = expand(Path("folder/subfolder"))
    assert isinstance(path, Path)
