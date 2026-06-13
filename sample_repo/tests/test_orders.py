from orders import Cart


def test_subtotal():
    cart = Cart([(100, 1), (10, 2)])
    assert cart.subtotal() == 120


def test_total_applies_tax():
    cart = Cart([(100, 1)])
    assert cart.total(0.25) == 125
