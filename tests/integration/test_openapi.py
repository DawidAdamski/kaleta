# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration tests for the Public API OpenAPI schema."""

from __future__ import annotations

from kaleta.main import _api_spec


class TestOpenApiSchema:
    def test_openapi_lists_core_resource_endpoints(self) -> None:
        """Covers: KAL-API-003

        The generated OpenAPI document lists the public REST endpoints with
        request and response schemas for core resources.
        """
        spec = _api_spec()
        paths = spec.get("paths", {})

        expected_paths = [
            "/api/v1/accounts/",
            "/api/v1/institutions/",
            "/api/v1/categories/",
            "/api/v1/transactions/",
            "/api/v1/budgets/",
            "/api/v1/payees/",
        ]
        for path in expected_paths:
            assert path in paths, f"Missing OpenAPI path: {path}"
            for method in ("get", "post"):
                if method in paths[path]:
                    operation = paths[path][method]
                    assert "responses" in operation
                    assert "200" in operation["responses"] or "201" in operation["responses"]

        components = spec.get("components", {}).get("schemas", {})
        assert "TransactionResponse" in components
        assert "BudgetResponse" in components
        assert "AccountResponse" in components
