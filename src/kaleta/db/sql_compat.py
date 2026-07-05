# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cross-database SQL helpers (SQLite + PostgreSQL)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import ColumnElement, extract
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.compiler import SQLCompiler
from sqlalchemy.sql.functions import FunctionElement
from sqlalchemy.types import Integer, String


def date_year(column: Any, *, label: str = "year") -> ColumnElement[Any]:
    return extract("year", column).label(label)


def date_month(column: Any, *, label: str = "month") -> ColumnElement[Any]:
    return extract("month", column).label(label)


class _YearMonth(FunctionElement[Any]):
    type = String()
    inherit_cache = True
    name = "year_month"


class _Weekday(FunctionElement[Any]):
    type = Integer()
    inherit_cache = True
    name = "weekday"


def date_year_month(column: Any) -> _YearMonth:
    return _YearMonth(column)


def date_weekday(column: Any) -> _Weekday:
    return _Weekday(column)


@compiles(_YearMonth, "postgresql")
def _compile_year_month_postgresql(
    element: _YearMonth,
    compiler: SQLCompiler,
    **kw: Any,
) -> str:
    col = compiler.process(element.clauses.clauses[0], **kw)
    return f"to_char({col}, 'YYYY-MM')"


@compiles(_YearMonth, "sqlite")
def _compile_year_month_sqlite(
    element: _YearMonth,
    compiler: SQLCompiler,
    **kw: Any,
) -> str:
    col = compiler.process(element.clauses.clauses[0], **kw)
    return f"strftime('%Y-%m', {col})"


@compiles(_Weekday, "postgresql")
def _compile_weekday_postgresql(
    element: _Weekday,
    compiler: SQLCompiler,
    **kw: Any,
) -> str:
    col = compiler.process(element.clauses.clauses[0], **kw)
    return f"CAST(EXTRACT(dow FROM {col}) AS INTEGER)"


@compiles(_Weekday, "sqlite")
def _compile_weekday_sqlite(
    element: _Weekday,
    compiler: SQLCompiler,
    **kw: Any,
) -> str:
    col = compiler.process(element.clauses.clauses[0], **kw)
    return f"CAST(strftime('%w', {col}) AS INTEGER)"
