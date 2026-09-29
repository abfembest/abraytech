"""
Paystack delivers every webhook event to the one URL set in its dashboard,
but three apps take Paystack payments, each with its own webhook view. Each
view calls forward_if_foreign() after checking the signature, so whichever
URL is configured, the event reaches the app that owns the reference (the
prefix each app gives its references when starting a payment).

The receiving view checks the signature again itself, with the same key.
"""

# (reference prefix, owning app) - see where each app builds its reference:
# store 'ord_' (store.views), consultation 'csl_' (consultation.views),
# admissions fees 'FEE' / 'APP-' (eduweb.paystack).
REFERENCE_OWNERS = (
    ('ord_', 'store'),
    ('csl_', 'consultation'),
    ('FEE', 'eduweb'),
    ('APP-', 'eduweb'),
)


def owner_of(reference):
    reference = reference or ''
    return next((app for prefix, app in REFERENCE_OWNERS if reference.startswith(prefix)), None)


def _webhook_view(app):
    if app == 'store':
        from apps.store.views import paystack_webhook
    elif app == 'consultation':
        from apps.consultation.views import paystack_webhook
    else:
        from apps.eduweb.paystack import paystack_webhook
    return paystack_webhook


def forward_if_foreign(request, current_app, reference):
    """The owning app's webhook response if `reference` belongs to another
    app, else None (the current view handles it)."""
    owner = owner_of(reference)
    if owner is None or owner == current_app:
        return None
    return _webhook_view(owner)(request)
