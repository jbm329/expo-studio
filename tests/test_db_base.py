import pytest
from unittest.mock import patch, MagicMock
from expo_jbm329.db import base
from expo_jbm329.db.core.models import ConnectionConfig, SqlResult

@pytest.fixture(autouse=True)
def clear_base_cache():
    """Clear the global services cache before each test."""
    with patch.dict(base._services, {}, clear=True):
        yield

def test_configure_timeouts():
    base.configure_timeouts(login_timeout_s=15, query_timeout_s=45)
    assert base._login_timeout_s == 15
    assert base._query_timeout_s == 45
    
    with pytest.raises(ValueError):
        base.configure_timeouts(login_timeout_s=-1)

@patch("expo_jbm329.db.base.read_connections")
def test_get_service_caching(mock_read_connections):
    # Setup mock connection
    mock_read_connections.return_value = {
        "test_conn": {"name": "test_conn", "engine": "sqlite"}
    }
    
    # First call - should create service
    service1, cfg1 = base._get_service_with_config("test_conn")
    assert "test_conn" in base._services
    
    # Second call - should return cached service
    service2, cfg2 = base._get_service_with_config("test_conn")
    assert service1 is service2
    assert cfg1 is cfg2

@patch("expo_jbm329.db.base.read_connections")
def test_close_connection(mock_read_connections):
    mock_read_connections.return_value = {
        "test_conn": {"name": "test_conn", "engine": "sqlite"}
    }
    
    service, cfg = base._get_service_with_config("test_conn")
    # Mock the dispose method to verify it's called
    service.dispose = MagicMock()
    
    base.close_connection("test_conn")
    assert "test_conn" not in base._services
    service.dispose.assert_called_once()

@patch("expo_jbm329.db.base._get_service_with_config")
def test_execute_sql_safe(mock_get_svc_cfg):
    mock_service = MagicMock()
    mock_cfg = ConnectionConfig(name="test", engine="sqlite", protocol="sqlite")
    mock_get_svc_cfg.return_value = (mock_service, mock_cfg)
    
    expected_result = SqlResult(ok=True)
    mock_service.execute_sql.return_value = expected_result
    
    result = base.execute_sql_safe("test", "SELECT 1")
    
    assert result == expected_result
    mock_service.execute_sql.assert_called_once_with(mock_cfg, "SELECT 1", top_n=None)

def test_execute_sql_safe_initialization_failure():
    with patch("expo_jbm329.db.base._build_connection_config") as mock_build:
        mock_build.side_effect = RuntimeError("Config missing")
        
        result = base.execute_sql_safe("nonexistent", "SELECT 1")
        
        assert result.ok is False
        assert result.error.category == "connection"
        assert "Could not initialize connection" in result.error.message
        assert "Config missing" in result.error.hint

def test_list_tables_failure():
    with patch("expo_jbm329.db.base._get_service_with_config") as mock_get:
        mock_get.side_effect = Exception("Service fail")
        
        with pytest.raises(Exception, match="Service fail"):
            base.list_tables("broken_conn")

def test_build_connection_config_sqlite():
    # We can test the logic of config building without mocking read_connections if we patch it
    with patch("expo_jbm329.db.base.read_connections") as mock_read:
        mock_read.return_value = {"my_sqlite": {"name": "my_sqlite", "db_type": "sqlite", "database": "test.db"}}
        
        cfg = base._build_connection_config("my_sqlite")
        assert cfg.name == "my_sqlite"
        assert cfg.engine == "sqlite"
        assert cfg.protocol == "sqlite"
        assert cfg.database == "test.db"

def test_build_connection_config_mysql():
    with patch("expo_jbm329.db.base.read_connections") as mock_read:
        mock_read.return_value = {"my_mysql": {
            "name": "my_mysql", 
            "db_type": "mysql", 
            "protocol": "pymysql",
            "server": "localhost",
            "user": "root"
        }}
        
        cfg = base._build_connection_config("my_mysql")
        assert cfg.engine == "mysql"
        assert cfg.protocol == "pymysql"
        assert cfg.server == "localhost"
