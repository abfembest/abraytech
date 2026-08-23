import hashlib
import hmac
import json
import logging
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F, Q
from django.db.models.functions import Greatest
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.eduweb.models import AuditLog, UserProfile
from apps.eduweb.views import generate_captcha

from . import cart, services
from .decorators import store_access
from .emailservices import (
    send_order_confirmation_email,
    send_refund_request_staff_notification,
    send_staff_order_notification,
    send_store_password_reset_email,
)
from .models import Order, OrderItem, Product, ProductCategory, ProductVariant

logger = logging.getLogger(__name__)

SIGNUP_CAPTCHA_SESSION_KEY = 'store_signup_captcha_answer'
LOGIN_CAPTCHA_SESSION_KEY = 'store_login_captcha_answer'


def _stash_login_captcha(request):
    """Generate + stash a math captcha for a store login form — the same
    generate_captcha() eduweb:auth_page uses for its own sign-in, so store
    login gets the same bot-resistance rather than relying on the honeypot
    alone."""
    question, answer = generate_captcha()
    request.session[LOGIN_CAPTCHA_SESSION_KEY] = answer
    return question


# =============================================================================
# BROWSING
# =============================================================================

@store_access
def store_list(request):
    category_slug = request.GET.get('category')
    query = request.GET.get('q', '').strip()

    products = (
        Product.objects.filter(is_active=True)
        .select_related('category')
        .prefetch_related('images__asset')
    )
    if category_slug:
        products = products.filter(category__slug=category_slug)
    if query:
        products = products.filter(
            Q(title__icontains=query) | Q(brand__icontains=query) | Q(summary__icontains=query)
        )

    paginator = Paginator(products, 12)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'products': page_obj.object_list,
        'page_obj': page_obj,
        'categories': ProductCategory.objects.all(),
        'active_category': category_slug,
        'query': query,
    }

    # HTMX-driven pagination (no page reload) only ever needs the grid
    # fragment — the login modal lives outside it and isn't re-rendered on
    # a page click, so skip regenerating its captcha here. Doing so on
    # every paginate click would silently invalidate whatever question is
    # already showing in an open modal without updating what the visitor
    # sees, making a correct answer fail.
    if request.headers.get('HX-Request') == 'true':
        return render(request, '_store_product_grid.html', context)

    if not _is_store_customer(request.user):
        context['login_captcha_question'] = _stash_login_captcha(request)
    return render(request, 'store.html', context)


@store_access
def product_detail(request, slug):
    product = get_object_or_404(Product, slug=slug, is_active=True)

    others = Product.objects.filter(is_active=True).exclude(pk=product.pk)
    others = others.filter(category=product.category) if product.category_id else others

    return render(request, 'product_detail.html', {
        'product': product,
        'images': product.images.select_related('asset').all(),
        'specifications': product.specifications.all(),
        'variants': product.variants.all(),
        'other_products': others[:4],
    })


# =============================================================================
# CART
# =============================================================================

@store_access
@require_POST
def cart_add(request):
    product_id = request.POST.get('product_id')
    variant_id = request.POST.get('variant_id') or None
    try:
        quantity = int(request.POST.get('quantity', 1))
    except (TypeError, ValueError):
        quantity = 1
    if quantity <= 0:
        quantity = 1

    product = Product.objects.filter(id=product_id, is_active=True).first()
    if product is None or product.price is None:
        return JsonResponse(
            {'success': False, 'error': 'This product is not available for purchase.'},
            status=400,
        )

    # Any product that defines options (size, color, ...) must have one
    # picked before it can be added — never silently add a "no option"
    # line for a product that needs one.
    if product.variants.exists():
        if not variant_id or not product.variants.filter(id=variant_id).exists():
            return JsonResponse(
                {'success': False, 'error': 'Please select an option before adding to cart.'},
                status=400,
            )

    cart.add_to_cart(request.session, product.id, quantity, variant_id)
    return JsonResponse({'success': True, 'cart_count': cart.get_cart_count(request.session)})


@store_access
def cart_view(request):
    """GET renders the full cart page; an HTMX request (the slide-in cart
    drawer, or a quantity update/remove posted from inside it) instead gets
    just the cart_drawer.html fragment swapped into #cartDrawerContent, so
    the drawer stays open and in place rather than navigating away."""
    is_htmx = request.headers.get('HX-Request') == 'true'

    if request.method == 'POST':
        action = request.POST.get('action')
        key = request.POST.get('cart_key')

        if action == 'update':
            try:
                quantity = int(request.POST.get('quantity', 1))
            except (TypeError, ValueError):
                quantity = 1
            cart.set_quantity(request.session, key, quantity)
        elif action == 'remove':
            cart.remove_from_cart(request.session, key)

        if is_htmx:
            return render(request, 'cart_drawer.html', {
                'items': cart.get_cart_items(request.session),
                'total': cart.get_cart_total(request.session),
            })
        return redirect('store:cart_view')

    template = 'cart_drawer.html' if is_htmx else 'cart.html'
    return render(request, template, {
        'items': cart.get_cart_items(request.session),
        'total': cart.get_cart_total(request.session),
    })


# =============================================================================
# CHECKOUT — store accounts are deliberately separate from LMS accounts.
# request.user is only ever treated as the buyer when profile.role ==
# 'customer'; anonymous users and every other LMS role see the store's own
# sign-up/log-in gate, never a silent checkout under their LMS identity.
# =============================================================================

def _is_store_customer(user):
    return user.is_authenticated and hasattr(user, 'profile') and user.profile.role == 'customer'


def _create_order_and_pay(request, items, total, delivery):
    """Server-computed order creation + Paystack initialize, shared by the
    already-a-customer and just-signed-up-or-logged-in-as-customer paths.
    `items`/`total` come from cart.get_cart_items/get_cart_total, which are
    themselves built from Product.price — never from client POST data."""
    # Remember these details on the account (UserProfile already carries
    # phone/address/city for every role — reused here rather than a new
    # store-only table) so the next checkout/Account Details page starts
    # prefilled instead of asking again.
    profile = request.user.profile
    profile.phone = delivery['phone']
    profile.address = delivery['address']
    profile.city = delivery['city']
    profile.state = delivery['state']
    profile.save(update_fields=['phone', 'address', 'city', 'state'])

    with transaction.atomic():
        order = Order.objects.create(
            user=request.user,
            buyer_name=request.user.get_full_name() or request.user.username,
            buyer_email=request.user.email,
            delivery_phone=delivery['phone'],
            delivery_address=delivery['address'],
            delivery_city=delivery['city'],
            delivery_state=delivery['state'],
            amount=total,
            currency='NGN',
            status='pending',
            payment_reference=f"ord_{uuid.uuid4().hex}",
        )
        for item in items:
            variant = item['variant']
            OrderItem.objects.create(
                order=order,
                product=item['product'],
                product_title=item['product'].title,
                variant_label=f"{variant.option_name}: {variant.value}" if variant else '',
                unit_price=item['product'].price,
                currency='NGN',
                quantity=item['quantity'],
            )

    data = services.initialize_transaction(order, request)
    if data.get('status'):
        # Cart is cleared only once payment is confirmed (checkout_callback,
        # after _confirm_paid_order marks the order 'paid') — not here, or
        # abandoning the Paystack page and coming back would find an empty
        # cart despite never having paid.
        return redirect(data['data']['authorization_url'])

    order.status = 'failed'
    order.save(update_fields=['status'])
    messages.error(request, 'Could not start payment right now. Please try again.')
    return redirect('store:cart_view')


@store_access
def checkout_view(request):
    items = cart.get_cart_items(request.session)
    if not items:
        messages.warning(request, 'Your cart is empty.')
        return redirect('store:cart_view')
    total = cart.get_cart_total(request.session)

    is_customer = _is_store_customer(request.user)

    if request.method == 'GET':
        context = {'items': items, 'total': total, 'is_customer': is_customer}
        if not is_customer:
            captcha_question, captcha_answer = generate_captcha()
            request.session[SIGNUP_CAPTCHA_SESSION_KEY] = captcha_answer
            context['captcha_question'] = captcha_question
            context['login_captcha_question'] = _stash_login_captcha(request)
        else:
            # Prefill from the account's saved delivery details (Account
            # Details page / a previous order) so a returning customer
            # doesn't retype their address every time.
            profile = request.user.profile
            context['delivery'] = {
                'phone': profile.phone,
                'address': profile.address,
                'city': profile.city,
                'state': profile.state,
            }
        return render(request, 'checkout.html', context)

    # ── POST ─────────────────────────────────────────────────────────────
    delivery = {
        'phone': request.POST.get('delivery_phone', '').strip(),
        'address': request.POST.get('delivery_address', '').strip(),
        'city': request.POST.get('delivery_city', '').strip(),
        'state': request.POST.get('delivery_state', '').strip(),
    }

    def _delivery_missing():
        return not (delivery['phone'] and delivery['address'] and delivery['city'] and delivery['state'])

    if not is_customer:
        if request.POST.get('action') != 'signup':
            messages.error(request, 'Please sign up or log in to continue.')
            return redirect('store:checkout_view')

        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        captcha = request.POST.get('captcha', '').strip()

        def _signup_error(msg):
            q, a = generate_captcha()
            request.session[SIGNUP_CAPTCHA_SESSION_KEY] = a
            messages.error(request, msg)
            return render(request, 'checkout.html', {
                'items': items,
                'total': total,
                'is_customer': False,
                'captcha_question': q,
                'login_captcha_question': _stash_login_captcha(request),
                'signup_error': msg,
                'name': name,
                'email': email,
                'delivery': delivery,
            })

        if not name or not email or not password:
            return _signup_error('Name, email, and password are all required.')

        if _delivery_missing():
            return _signup_error('Please fill in your delivery phone, address, city, and state.')

        session_answer = request.session.get(SIGNUP_CAPTCHA_SESSION_KEY)
        try:
            if int(captcha) != int(session_answer):
                return _signup_error('Incorrect captcha answer. Please try again.')
        except (ValueError, TypeError):
            return _signup_error('Invalid captcha answer. Enter a number.')

        if User.objects.filter(email__iexact=email).exists():
            return _signup_error('An account with this email already exists — please log in instead.')

        with transaction.atomic():
            username = f"{email.split('@')[0][:20]}_{uuid.uuid4().hex[:8]}"
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=name,
                is_active=True,
            )
            user.profile.role = 'customer'
            user.profile.email_verified = True
            user.profile.save(update_fields=['role', 'email_verified'])

        login(request, user)
        request.session.pop(SIGNUP_CAPTCHA_SESSION_KEY, None)

    elif _delivery_missing():
        messages.error(request, 'Please fill in your delivery phone, address, city, and state.')
        return render(request, 'checkout.html', {
            'items': items,
            'total': total,
            'is_customer': True,
            'delivery': delivery,
        })

    return _create_order_and_pay(request, items, total, delivery)


@require_POST
def store_login(request):
    """Returning-customer login — deliberately separate from
    eduweb:auth_page. Only succeeds for a profile.role == 'customer'
    account; an LMS account entered here is rejected so the two systems
    never silently merge through this door. Redirects to `next` (POST field,
    falling back to checkout) so this same view can be reused from both the
    checkout page and the "My Orders" page's sign-in prompt."""
    email = request.POST.get('email', '').strip()
    password = request.POST.get('password', '')
    next_url = request.POST.get('next') or 'store:checkout_view'

    def _redirect_next():
        return redirect(next_url) if next_url.startswith('/') else redirect(next_url)

    session_answer = request.session.pop(LOGIN_CAPTCHA_SESSION_KEY, None)
    try:
        if int(request.POST.get('captcha', '')) != int(session_answer):
            messages.error(request, 'Incorrect captcha answer. Please try again.')
            return _redirect_next()
    except (ValueError, TypeError):
        messages.error(request, 'Invalid captcha answer. Enter a number.')
        return _redirect_next()

    username = None
    try:
        username = User.objects.get(email__iexact=email).username
    except User.DoesNotExist:
        pass

    user = authenticate(request, username=username, password=password) if username else None

    if user is None:
        messages.error(request, 'Invalid email or password.')
        return _redirect_next()

    if not hasattr(user, 'profile') or user.profile.role != 'customer':
        messages.error(
            request,
            'This is the store login — use your regular sign-in to access your student/staff account.'
        )
        return _redirect_next()

    login(request, user)
    return _redirect_next()


# =============================================================================
# PASSWORD RESET — link-based, matching eduweb.views.forgot_password/
# reset_password exactly (same UserProfile.generate_password_reset_token()/
# is_reset_token_valid()/clear_reset_token(), same 1-hour expiry, same
# no-enumeration silence on an unknown email), just pointed at the store's
# own login/email.
# =============================================================================

def forgot_password(request):
    """Display forgot-password form and dispatch the reset-link email."""
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        user = User.objects.filter(email__iexact=email, profile__role='customer', is_active=True).first()

        if user:
            if not send_store_password_reset_email(request, user):
                logger.error("Store password reset email failed silently for %s", email)

        # Always show the same success screen to prevent email enumeration
        return render(request, 'store_forgot_password.html', {
            'email_sent': True,
            'submitted_email': email,
        })

    return render(request, 'store_forgot_password.html')


def reset_password(request, token):
    """Validate the reset token and let the user set a new password."""
    try:
        profile = UserProfile.objects.get(password_reset_token=token, role='customer')
    except UserProfile.DoesNotExist:
        messages.error(request, 'Invalid or expired password reset link.')
        return redirect('store:forgot_password')

    if not profile.is_reset_token_valid():
        profile.clear_reset_token()
        messages.error(request, 'This reset link has expired. Please request a new one.')
        return redirect('store:forgot_password')

    user = profile.user

    if request.method == 'POST':
        new_password      = request.POST.get('password1', '')
        confirm_password  = request.POST.get('password2', '')

        if not new_password or new_password != confirm_password:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'store_reset_password.html', {'token': token})

        try:
            validate_password(new_password, user=user)
        except ValidationError as e:
            for err in e.messages:
                messages.error(request, err)
            return render(request, 'store_reset_password.html', {'token': token})

        user.set_password(new_password)
        user.save(update_fields=['password'])
        profile.clear_reset_token()

        AuditLog.objects.create(
            user=user,
            action='update',
            model_name='User',
            object_id=str(user.pk),
            description=f'{user.username} reset their store account password via the forgot-password link.',
        )

        messages.success(request, 'Your password has been reset successfully. You can now log in.')
        return redirect('store:store_list')

    return render(request, 'store_reset_password.html', {'token': token})


# =============================================================================
# PAYMENT CONFIRMATION — shared idempotent helper used by both the
# redirect-back callback and the webhook, so a replayed webhook or a
# callback-after-webhook is always a safe no-op. Order emails (confirmation
# to buyer, fulfillment alert to staff) live in emailservices.py.
# =============================================================================

def _confirm_paid_order(order, data):
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.status != 'paid':
            # Paystack reporting "success" isn't enough on its own — verify
            # the amount/currency it actually charged matches what this
            # order expects before treating it as paid. Without this check
            # a replayed or forged reference for a *different, cheaper*
            # transaction could be swapped in against this order's ID.
            expected_kobo = int(order.amount * 100)
            paid_kobo = data.get('amount')
            paid_currency = (data.get('currency') or '').upper()
            if paid_kobo != expected_kobo or (paid_currency and paid_currency != order.currency):
                logger.warning(
                    'Paystack amount/currency mismatch for %s: expected %s kobo %s, got %s kobo %s',
                    order.order_number, expected_kobo, order.currency, paid_kobo, paid_currency,
                )
                order.status = 'failed'
                order.payment_metadata = data
                order.save(update_fields=['status', 'payment_metadata', 'updated_at'])
                AuditLog.objects.create(
                    user=order.user,
                    action='update',
                    model_name='Order',
                    object_id=str(order.id),
                    description=f'Payment amount mismatch for {order.order_number} (ref {order.payment_reference}) — flagged failed, not fulfilled.',
                )
                return order

            order.status = 'paid'
            order.paid_at = timezone.now()
            order.gateway_payment_id = str(data.get('id', ''))
            order.payment_metadata = data
            order.save(update_fields=['status', 'paid_at', 'gateway_payment_id', 'payment_metadata', 'updated_at'])

            # Deduct stock now — the cart only ever *capped* the requested
            # quantity at whatever stock looked available at add-to-cart
            # time, it never actually reserved or removed it. This is the
            # one place a paid order is guaranteed to only be processed
            # once (guarded by the status check above + select_for_update),
            # so it's the right — and only — place stock actually leaves
            # inventory. Greatest(..., 0) keeps a pathological race (two
            # simultaneous purchases both seeing "enough" stock) from ever
            # showing a negative count, at the cost of allowing that rare
            # case to oversell by a unit rather than fail the payment that
            # already succeeded on Paystack's side.
            for item in order.items.select_related('product').all():
                if item.product and item.product.track_inventory:
                    Product.objects.filter(pk=item.product_id).update(
                        stock_quantity=Greatest(F('stock_quantity') - item.quantity, 0)
                    )

            send_order_confirmation_email(order)
            send_staff_order_notification(order)
            AuditLog.objects.create(
                user=order.user,
                action='update',
                model_name='Order',
                object_id=str(order.id),
                description=f'Payment confirmed for {order.order_number} (ref {order.payment_reference}).',
            )
    return order


@store_access
def checkout_callback(request):
    reference = request.GET.get('reference')
    order = get_object_or_404(Order, payment_reference=reference)
    data = services.verify_transaction(reference)

    verified = bool(data.get('status') and data.get('data', {}).get('status') == 'success')
    if verified:
        order = _confirm_paid_order(order, data['data'])
        if order.status == 'paid':
            cart.clear_cart(request.session)
    elif order.status != 'paid':
        order.status = 'failed'
        order.save(update_fields=['status'])

    return render(request, 'order_confirmation.html', {'order': order, 'verified': verified})


@csrf_exempt
@require_POST
def paystack_webhook(request):
    signature = request.headers.get('X-Paystack-Signature', '')
    expected = hmac.new(
        services.get_paystack_secret_key().encode(), request.body, hashlib.sha512
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        logger.warning('Paystack webhook signature mismatch')
        return HttpResponse(status=400)

    try:
        event = json.loads(request.body)
    except (ValueError, TypeError):
        logger.warning('Paystack webhook: could not parse payload')
        return HttpResponse(status=200)

    if event.get('event') == 'charge.success':
        reference = event.get('data', {}).get('reference')
        order = Order.objects.filter(payment_reference=reference).first()
        if order is not None:
            _confirm_paid_order(order, event['data'])

    return HttpResponse(status=200)


# =============================================================================
# MY ORDERS — a customer's own order history. Gated on the same
# profile.role == 'customer' identity as checkout, not just "logged in":
# an LMS role (student/instructor/...) has no store orders of its own and
# must not see this as if it were their account area.
# =============================================================================

@store_access
def my_orders(request):
    if not _is_store_customer(request.user):
        return render(request, 'my_orders.html', {
            'is_customer': False,
            'next': 'store:my_orders',
            'login_captcha_question': _stash_login_captcha(request),
        })

    from django.contrib.humanize.templatetags.humanize import intcomma

    orders = (
        Order.objects.filter(user=request.user)
        .prefetch_related('items__product__images__asset')
        .order_by('-created_at')
    )

    def _item_image_url(item):
        if item.product_id is None:
            return None
        image = item.product.primary_image
        return image.asset.file.url if image else None

    # Flat, JSON-serializable rows for the DataTable — pre-formatted here
    # (not left to the JS) so currency/date rendering stays identical to
    # every other NGN amount on the site (server-side intcomma, not a
    # reimplementation in JS).
    orders_data = [{
        'order_number': order.order_number,
        'created_at': order.created_at.strftime('%d %b %Y, %H:%M'),
        'status': order.status,
        'status_display': order.get_status_display(),
        'total_display': f"NGN {intcomma(int(order.amount))}",
        'delivery_display': f"{order.delivery_address}, {order.delivery_city}, {order.delivery_state}" if order.delivery_address else '',
        'delivery_phone': order.delivery_phone,
        'can_request_refund': order.can_be_refunded and order.refund_request_status in ('none', 'rejected'),
        'refund_request_status': order.refund_request_status,
        'items': [{
            'title': item.product_title,
            'variant_label': item.variant_label,
            'quantity': item.quantity,
            'image_url': _item_image_url(item),
            'unit_price_display': f"NGN {intcomma(int(item.unit_price))}",
            'line_total_display': f"NGN {intcomma(int(item.line_total))}",
        } for item in order.items.all()],
    } for order in orders]

    return render(request, 'my_orders.html', {
        'is_customer': True,
        'orders': orders,
        'orders_data': orders_data,
    })


@store_access
@require_POST
def request_refund(request, order_number):
    """Customer-initiated cancel/refund request — never touches the order's
    status or money directly. It only flags the order for staff review;
    staff must approve it (which actually calls Paystack) or reject it from
    the admin order detail page. See management.views.order_detail."""
    if not _is_store_customer(request.user):
        messages.error(request, 'Please sign in to manage your orders.')
        return redirect('store:my_orders')

    order = get_object_or_404(Order, order_number=order_number, user=request.user)

    if not order.can_be_refunded:
        messages.error(request, f'Order {order.order_number} is not eligible for a refund request.')
        return redirect('store:my_orders')

    if order.refund_request_status == 'pending':
        messages.info(request, f'A refund request for {order.order_number} is already pending review.')
        return redirect('store:my_orders')

    reason = request.POST.get('reason', '').strip()
    if not reason:
        messages.error(request, 'Please tell us why you want to cancel/return this order.')
        return redirect('store:my_orders')

    order.refund_request_status = 'pending'
    order.refund_requested_at = timezone.now()
    order.refund_request_reason = reason
    order.save(update_fields=['refund_request_status', 'refund_requested_at', 'refund_request_reason'])

    AuditLog.objects.create(
        user=request.user, action='update', model_name='Order', object_id=str(order.id),
        description=f'Customer requested a refund/cancellation for {order.order_number}.'
    )
    send_refund_request_staff_notification(order)

    messages.success(request, f'Your request for {order.order_number} has been sent to our team for review.')
    return redirect('store:my_orders')


# =============================================================================
# ACCOUNT DETAILS — contact/delivery info a customer can review and update
# outside of checkout. Reuses eduweb.UserProfile's existing phone/address/
# city/state fields (every role already has these) rather than a new
# store-only table — checkout both prefills from and saves back to the same
# fields, so this page and checkout always agree.
# =============================================================================

@store_access
def store_profile(request):
    if not _is_store_customer(request.user):
        return render(request, 'store_profile.html', {
            'is_customer': False,
            'next': 'store:store_profile',
            'login_captcha_question': _stash_login_captcha(request),
        })

    profile = request.user.profile

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        phone = request.POST.get('phone', '').strip()
        address = request.POST.get('address', '').strip()
        city = request.POST.get('city', '').strip()
        state = request.POST.get('state', '').strip()

        if not (name and phone and address and city and state):
            messages.error(request, 'Please fill in all fields.')
        else:
            request.user.first_name = name
            request.user.save(update_fields=['first_name'])
            profile.phone = phone
            profile.address = address
            profile.city = city
            profile.state = state
            profile.save(update_fields=['phone', 'address', 'city', 'state'])
            messages.success(request, 'Your details have been saved.')
        return redirect('store:store_profile')

    return render(request, 'store_profile.html', {
        'is_customer': True,
        'profile': profile,
    })
