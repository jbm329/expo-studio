"""REST API samples."""
from __future__ import annotations

import json

from expo_jbm329.services.rest.models import (
    RestAuthConfig,
    RestRequestConfig,
)
from expo_jbm329.utils.path_manager import get_bootstrap_root


def load_rest_samples() -> list[RestRequestConfig]:
    """Load built-in REST API sample connections.

    The returned connections are:
      - runtime-only
      - read-only
      - intended for demonstration and learning

    Returns:
        A list of RestRequestConfig instances.
    """
    path = get_bootstrap_root() / "rest" / "rest_samples.json"
    data = json.loads(path.read_text(encoding="utf-8"))

    samples: list[RestRequestConfig] = []

    for rec in data.get("connections", []):
        auth_cfg = None
        auth_raw = rec.get("auth")
        if isinstance(auth_raw, dict):
            auth_cfg = RestAuthConfig(
                type=str(auth_raw.get("type", "none")),
                token=auth_raw.get("token"),
                username=auth_raw.get("username"),
                password=auth_raw.get("password"),
            )

        # Normalize response_path
        rp = rec.get("response_path")
        if not isinstance(rp, str) or rp.strip() in ("", "None"):
            rp = None

        req = RestRequestConfig(
            name=rec["name"],
            url=rec["url"],
            method=rec.get("method", "GET"),
            json_body=rec.get("json_body"),
            headers=rec.get("headers", {}),
            query_params=rec.get("query_params", {}),
            response_path=rp,
            auth=auth_cfg,
        )

        # Fail fast if sample definition is broken
        req.validate()
        samples.append(req)

    return samples
