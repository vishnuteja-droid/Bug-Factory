import pytest

from calc import add, subtract, multiply, divide, percentage


def test_add():
    assert add(2, 3) == 5


def test_subtract():
    assert subtract(10, 3) == 7


def test_multiply():
    assert multiply(4, 5) == 20


def test_divide():
    assert divide(10, 2) == 5


def test_divide_by_zero():
    with pytest.raises(ValueError):
        divide(1, 0)


def test_percentage():
    assert percentage(50, 200) == 25
