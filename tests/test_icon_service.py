
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap

from expo_jbm329.workbench.icon.icon_service import IconService
from tests.stubs import DummyThemeService


@pytest.fixture
def theme_service():
    return DummyThemeService("light")

@pytest.fixture
def icon_service(qt_app, theme_service):
    # logger = MagicMock()
    return IconService(theme_service)

def test_init(theme_service, qt_app):
    """Verifies initialization and signal connection."""
    # We must mock _on_theme_changed BEFORE creating IconService 
    # OR we don't mock it and just verify side effects.
    # Let's verify side effects: icons_updated signal emission.
    icon_service = IconService(theme_service)
    assert icon_service._theme_service == theme_service
    
    spy = MagicMock()
    icon_service.icons_updated.connect(spy)
    theme_service.set_theme("dark")
    spy.assert_called_once()

def test_on_theme_changed(qt_app, icon_service):
    """Verifies QPixmapCache clear and icons_updated signal."""
    with patch('PyQt6.QtGui.QPixmapCache.clear') as mock_clear:
        # Connect a spy to the signal
        spy = MagicMock()
        icon_service.icons_updated.connect(spy)
        
        icon_service._on_theme_changed("dark")
        
        mock_clear.assert_called_once()
        spy.assert_called_once()

def test_current_theme(icon_service, theme_service):
    """Verifies proxying to ThemeService."""
    theme_service.theme = "custom-theme"
    assert icon_service.current_theme() == "custom-theme"

def test_make_disabled_pixmap_light(qt_app, icon_service):
    """Verifies disabled pixmap generation for light mode (dark overlay)."""
    pix = QPixmap(10, 10)
    pix.fill(Qt.GlobalColor.red)
    
    # dark_mode=True means original icons are light -> overlay dark shade
    disabled = icon_service._make_disabled_pixmap(pix, dark_mode=True)
    assert not disabled.isNull()
    assert disabled.size() == pix.size()

def test_make_disabled_pixmap_dark(qt_app, icon_service):
    """Verifies disabled pixmap generation for dark mode (light overlay)."""
    pix = QPixmap(10, 10)
    pix.fill(Qt.GlobalColor.red)
    
    # dark_mode=False means original icons are dark -> overlay light shade
    disabled = icon_service._make_disabled_pixmap(pix, dark_mode=False)
    assert not disabled.isNull()
    assert disabled.size() == pix.size()

def test_get_icon(qt_app, icon_service, theme_service):
    """Verifies icon retrieval and disabled variant generation."""
    # We need to mock QPixmap to avoid looking for real files in QRC
    # Patching at the module level where IconService is defined
    with patch('expo_jbm329.workbench.icon.icon_service.QPixmap') as mock_pixmap_cls:
        # Create a REAL QPixmap but empty, so QIcon.addPixmap doesn't complain about MagicMock
        mock_pix = QPixmap(16, 16)
        mock_pixmap_cls.return_value = mock_pix
        
        # Also need to mock _make_disabled_pixmap because it uses QPainter on real Pixmaps
        disabled_pix = QPixmap(16, 16)
        with patch.object(icon_service, '_make_disabled_pixmap', return_value=disabled_pix) as mock_make_disabled:
            icon = icon_service.get("test_icon")
            
            assert isinstance(icon, QIcon)
            # Verify path construction
            mock_pixmap_cls.assert_called_with(":/icons/light/test_icon.png")
            # Verify disabled variant created
            mock_make_disabled.assert_called_once()
