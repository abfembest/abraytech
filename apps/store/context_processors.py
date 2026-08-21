from . import cart


def cart_context(request):
    """Inject the cart badge count into every template. Fail-safe (mirrors
    apps.eduweb.context.admin_counts) so a broken session or DB hiccup never
    breaks page rendering site-wide."""
    try:
        return {'cart_count': cart.get_cart_count(request.session)}
    except Exception:
        return {'cart_count': 0}
