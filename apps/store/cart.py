"""Session-based shopping cart. `request.session['cart']` is a plain dict of
{cart_key: quantity} — no separate Cart model, matching this project's
preference for the simplest thing that works.

`cart_key` is `"<product_id>:<variant_id>"` (variant_id is `0` for a product
with no selected variant) so the same product can sit in the cart more than
once with different variants (e.g. a hoodie in Size S and Size L as two
separate lines)."""

from .models import Product, ProductVariant

CART_SESSION_KEY = 'cart'


def cart_key(product_id, variant_id=None):
    return f"{product_id}:{variant_id or 0}"


def _get_cart(session):
    return session.setdefault(CART_SESSION_KEY, {})


def add_to_cart(session, product_id, quantity=1, variant_id=None):
    cart = _get_cart(session)
    key = cart_key(product_id, variant_id)
    cart[key] = cart.get(key, 0) + quantity
    session.modified = True


def set_quantity(session, key, quantity):
    cart = _get_cart(session)
    if quantity <= 0:
        cart.pop(key, None)
    else:
        cart[key] = quantity
    session.modified = True


def remove_from_cart(session, key):
    cart = _get_cart(session)
    cart.pop(key, None)
    session.modified = True


def clear_cart(session):
    session[CART_SESSION_KEY] = {}
    session.modified = True


def get_cart_items(session):
    """Return a list of dicts: cart_key, product, variant (or None),
    quantity, line_total.

    Skips deactivated products and price-less ("Contact for pricing")
    products — those can never enter cart/checkout. If a product tracks
    inventory, the requested quantity is silently capped at the current
    stock level rather than erroring. A variant that's since been deleted
    is silently dropped from its line (the product itself stays, just
    without a variant label) rather than erroring the whole cart.
    """
    cart = _get_cart(session)
    if not cart:
        return []

    parsed = []
    for key, quantity in cart.items():
        if quantity <= 0:
            continue
        try:
            pid_str, vid_str = key.split(':', 1)
        except ValueError:
            continue
        parsed.append((key, pid_str, vid_str, quantity))

    product_ids = {p for _, p, _, _ in parsed}
    variant_ids = {v for _, _, v, _ in parsed if v != '0'}
    products = {str(p.id): p for p in Product.objects.filter(id__in=product_ids, is_active=True)}
    variants = {str(v.id): v for v in ProductVariant.objects.filter(id__in=variant_ids)}

    items = []
    for key, pid_str, vid_str, quantity in parsed:
        product = products.get(pid_str)
        if not product or product.price is None:
            continue
        if product.track_inventory:
            quantity = min(quantity, product.stock_quantity)
        if quantity <= 0:
            continue
        variant = variants.get(vid_str) if vid_str != '0' else None
        line_total = product.price * quantity
        items.append({
            'cart_key': key, 'product': product, 'variant': variant,
            'quantity': quantity, 'line_total': line_total,
        })
    return items


def get_cart_count(session):
    return sum(item['quantity'] for item in get_cart_items(session))


def get_cart_total(session):
    return sum((item['line_total'] for item in get_cart_items(session)), 0)
