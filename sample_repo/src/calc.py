"""A tiny calculator library used by the bug-factory demo."""


def add(a, b):
    return a + b


def subtract(a, b):
    # BUG: this adds instead of subtracting.
    return a + b


def multiply(a, b):
    return a * b


def divide(a, b):
    if b == 0:
        raise ValueError("cannot divide by zero")
    return a / b


def percentage(part, whole):
    return (part / whole) * 100
