"""Shopping-cart order math — used to exercise class/method-level fixes."""


class Cart:
    def __init__(self, items):
        # items: list of (unit_price, quantity)
        self.items = items

    def subtotal(self):
        return sum(price * qty for price, qty in self.items)

    def total(self, tax_rate):
        # BUG: returns the pre-tax subtotal; tax is never applied.
        return self.subtotal()
