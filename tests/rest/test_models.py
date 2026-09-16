from __future__ import annotations

import pytest

from expo_jbm329.services.rest.models import RestAuthConfig, RestRequestConfig


def test_rest_request_config_rejects_post_without_body():
    cfg = RestRequestConfig(
        name="Example",
        url="https://example.com",
        method="POST",
        json_body=None,
    )

    with pytest.raises(ValueError, match="POST requests require a JSON body"):
        cfg.validate()


def test_rest_auth_config_validates_basic_auth_requirements():
    auth = RestAuthConfig(type="basic", username="", password="")

    with pytest.raises(ValueError, match="Basic auth requires username and password"):
        auth.validate()


def test_rest_auth_config_validates_api_key_requirements():
    auth = RestAuthConfig(
        type="api_key",
        api_key_name="X-API-Key",
        api_key_value="secret",
        api_key_location="header",
    )

    auth.validate()


def test_rest_request_config_validates_nested_auth():
    cfg = RestRequestConfig(
        name="Example",
        url="https://example.com",
        json_body=None,
        auth=RestAuthConfig(
            type="api_key",
            api_key_name="",
            api_key_value="secret",
            api_key_location="header",
        ),
    )

    with pytest.raises(ValueError, match="API key auth requires parameter name"):
        cfg.validate()
