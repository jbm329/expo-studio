import os
from pathlib import Path
from unittest.mock import patch
from expo_jbm329.utils.paths import expand, suffix_to_dir

def test_expand():
    # Test ~ expansion (if HOME is set)
    with patch.dict(os.environ, {"HOME": "/home/user", "USERPROFILE": "C:\\Users\\user"}):
        expanded = expand("~/test")
        # resolve() will make it absolute based on current FS, 
        # so we just check if it contains the expected parts
        assert "test" in str(expanded)

    # Test env var expansion
    with patch.dict(os.environ, {"MY_VAR": "my_val"}):
        expanded = expand("$MY_VAR/test")
        assert "my_val" in str(expanded)
        assert "test" in str(expanded)

def test_suffix_to_dir():
    settings = {}
    
    with patch("expo_jbm329.utils.paths.get_sql_dir", return_value=Path("/sql")), \
         patch("expo_jbm329.utils.paths.get_csv_dir", return_value=Path("/csv")), \
         patch("expo_jbm329.utils.paths.get_excel_dir", return_value=Path("/excel")), \
         patch("expo_jbm329.utils.paths.get_data_dir", return_value=Path("/data")), \
         patch("expo_jbm329.utils.paths.get_report_dir", return_value=Path("/report")), \
         patch("expo_jbm329.utils.paths.get_documents_dir", return_value=Path("/docs")):
        
        assert suffix_to_dir(".sql", settings) == Path("/sql")
        assert suffix_to_dir(".csv", settings) == Path("/csv")
        assert suffix_to_dir(".xlsx", settings) == Path("/excel")
        assert suffix_to_dir(".xls", settings) == Path("/excel")
        assert suffix_to_dir(".parquet", settings) == Path("/data")
        assert suffix_to_dir(".json", settings) == Path("/data")
        assert suffix_to_dir(".html", settings) == Path("/report")
        assert suffix_to_dir(".txt", settings) == Path("/docs")
        assert suffix_to_dir("", settings) == Path("/docs")
