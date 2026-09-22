# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for kaleta.debug_info — the About tab's debug report.

The point of every test here is the same: the block a user pastes into a public
issue must not carry a secret.
"""

from __future__ import annotations

import pytest

from kaleta.debug_info import (
    MASK,
    DebugSection,
    build_sections,
    env_rows,
    mask_db_url,
    mask_env_value,
    sections_as_markdown,
    version_rows,
)


class TestMaskDbUrl:
    def test_postgres_password_is_replaced_and_the_rest_kept(self) -> None:
        masked = mask_db_url("postgresql+asyncpg://kaleta:s3cret@db.example:5432/kaleta")
        assert masked == f"postgresql+asyncpg://kaleta:{MASK}@db.example:5432/kaleta"
        assert "s3cret" not in masked

    def test_sqlite_url_has_no_credentials_to_mask(self) -> None:
        url = "sqlite+aiosqlite:////home/u/.kaleta/kaleta.db"
        assert mask_db_url(url) == url

    def test_password_containing_an_at_sign_still_goes(self) -> None:
        masked = mask_db_url("postgresql://u:p@ss@db:5432/k")
        assert "p@ss" not in masked
        assert masked == f"postgresql://u:{MASK}@db:5432/k"

    def test_a_url_without_a_password_is_left_alone(self) -> None:
        url = "postgresql://kaleta@db:5432/kaleta"
        assert mask_db_url(url) == url


class TestMaskEnvValue:
    @pytest.mark.parametrize(
        "name",
        [
            "KALETA_SECRET_KEY",
            "KALETA_API_TOKEN",
            "KALETA_SMTP_PASSWORD",
            "KALETA_ERROR_TRACKER_DSN",
            "KALETA_BUG_REPORT_WEBHOOK",
            "secret_key",
            "smtp_password",
        ],
    )
    def test_secret_names_are_masked(self, name: str) -> None:
        assert mask_env_value(name, "hunter2") == MASK

    def test_an_unset_secret_stays_empty_rather_than_looking_set(self) -> None:
        assert mask_env_value("KALETA_API_TOKEN", "") == ""

    def test_db_url_keeps_everything_but_the_password(self) -> None:
        value = mask_env_value("KALETA_DB_URL", "postgresql://u:pw@h/db")
        assert value == f"postgresql://u:{MASK}@h/db"

    @pytest.mark.parametrize(
        ("name", "value"),
        [("KALETA_PORT", "8080"), ("KALETA_MODE", "web"), ("KALETA_DEBUG", "true")],
    )
    def test_harmless_values_are_shown(self, name: str, value: str) -> None:
        assert mask_env_value(name, value) == value


class TestEnvRows:
    def test_only_kaleta_variables_are_listed_and_sorted(self) -> None:
        rows = env_rows(
            {
                "PATH": "/usr/bin",
                "KALETA_PORT": "8080",
                "KALETA_HOST": "0.0.0.0",
                "HOME": "/home/u",
            }
        )
        assert rows == [("KALETA_HOST", "0.0.0.0"), ("KALETA_PORT", "8080")]

    def test_a_secret_variable_is_listed_but_not_shown(self) -> None:
        rows = env_rows({"KALETA_SECRET_KEY": "top-secret"})
        assert rows == [("KALETA_SECRET_KEY", MASK)]


class TestSections:
    def test_versions_name_kaleta_and_python(self) -> None:
        keys = [key for key, _ in version_rows()]
        assert keys[:2] == ["Kaleta", "Python"]
        assert "nicegui" in keys
        assert "sqlalchemy" in keys

    def test_the_settings_section_masks_the_secret_key(self) -> None:
        sections = {section.title: section for section in build_sections()}
        rows = dict(sections["Settings in force"].rows)
        assert rows["secret_key"] == MASK
        assert rows["smtp_password"] in {MASK, ""}
        assert "***" in rows["db_url"] or rows["db_url"].startswith("sqlite")

    def test_storage_keys_are_reported_by_type_not_by_value(self) -> None:
        sections = {
            section.title: section for section in build_sections(storage_keys={"language": "str"})
        }
        assert sections["Session storage keys"].rows == [("language", "str")]

    def test_empty_sections_carry_a_note_instead_of_nothing(self) -> None:
        sections = {section.title: section for section in build_sections()}
        assert sections["Session storage keys"].rows == []
        assert sections["Session storage keys"].empty_note


class TestMarkdown:
    def test_a_table_is_rendered_per_section(self) -> None:
        markdown = sections_as_markdown(
            [DebugSection(title="Versions", rows=[("Kaleta", "0.1.0")])]
        )
        assert markdown.startswith("## Kaleta debug info")
        assert "### Versions" in markdown
        assert "| Kaleta | `0.1.0` |" in markdown

    def test_log_lines_go_into_a_fenced_block(self) -> None:
        markdown = sections_as_markdown([DebugSection(title="Recent log lines", lines=["a", "b"])])
        assert "```\na\nb\n```" in markdown

    def test_an_empty_section_says_so(self) -> None:
        markdown = sections_as_markdown([DebugSection(title="Env", empty_note="nothing set")])
        assert "_nothing set_" in markdown

    def test_the_whole_report_is_multi_line_markdown_without_the_secret_key(self) -> None:
        markdown = sections_as_markdown(build_sections())
        assert markdown.count("\n") > 10
        assert f"| secret_key | `{MASK}` |" in markdown
