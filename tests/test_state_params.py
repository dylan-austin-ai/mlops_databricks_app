"""Tests for state_service._to_parameter — typed statement parameters.

str() on every param sent literal 'None'/'True' strings to the warehouse;
found live during the first policy-pack sync (NULL INT column).
"""

from __future__ import annotations

from services.state_service import _to_parameter


def test_none_binds_as_null():
    p = _to_parameter("x", None)
    assert p.value is None


def test_bool_binds_typed_lowercase():
    p = _to_parameter("x", True)
    assert (p.value, p.type) == ("true", "BOOLEAN")
    assert _to_parameter("x", False).value == "false"


def test_int_binds_int():
    # date_sub()/make_interval() reject BIGINT args — small ints must be INT
    p = _to_parameter("x", 365)
    assert (p.value, p.type) == ("365", "INT")


def test_huge_int_binds_bigint():
    p = _to_parameter("x", 2**40)
    assert (p.value, p.type) == (str(2**40), "BIGINT")


def test_float_binds_double():
    p = _to_parameter("x", 2.5)
    assert (p.value, p.type) == ("2.5", "DOUBLE")


def test_str_stays_untyped_string():
    p = _to_parameter("x", "tier_2")
    assert p.value == "tier_2" and p.type is None
