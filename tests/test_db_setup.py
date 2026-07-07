"""Tests for db/setup.py statement splitting — semicolons in strings/comments.

The naive split(";") cut migration 003 mid-COMMENT-string on the first live
run; these pin the quote/comment-aware splitter.
"""

from __future__ import annotations

from db.setup import _split_statements


def test_plain_statements_split():
    assert _split_statements("SELECT 1;\nSELECT 2;") == ["SELECT 1", "SELECT 2"]


def test_semicolon_inside_string_literal_kept():
    sql = "ALTER TABLE t ADD COLUMNS (c STRING COMMENT 'disabled; logged override');\nSELECT 1"
    stmts = _split_statements(sql)
    assert len(stmts) == 2
    assert "disabled; logged override" in stmts[0]


def test_semicolon_inside_line_comment_kept():
    sql = "-- health signal; a run that stops changing\nCREATE TABLE x (a INT);"
    stmts = _split_statements(sql)
    assert len(stmts) == 1
    assert "CREATE TABLE x" in stmts[0]


def test_escaped_quote_stays_in_string():
    sql = "SELECT 'it''s; fine'; SELECT 2"
    stmts = _split_statements(sql)
    assert stmts == ["SELECT 'it''s; fine'", "SELECT 2"]


def test_trailing_statement_without_semicolon():
    assert _split_statements("SELECT 1") == ["SELECT 1"]
