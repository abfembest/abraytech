import uuid

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class ProductCategory(models.Model):
    """Store catalog category — powers listing filters and category nav."""
    title = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    icon = models.CharField(max_length=50, blank=True, help_text="Lucide icon name, e.g. 'laptop'")
    description = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name = 'Product Category'
        verbose_name_plural = 'Product Categories'
        ordering = ['title']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)


class Product(models.Model):
    """A store/gadget product. Pricing is optional — leave blank to show
    'Contact for pricing' instead of a fabricated number. Kept on the
    original `eduweb_product` table (see Meta.db_table) so moving this
    model out of eduweb into its own app didn't require copying data."""

    CONDITION_CHOICES = [
        ('new', 'New'),
        ('refurbished', 'Refurbished'),
        ('used', 'Used'),
    ]

    # Identity
    title = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170, unique=True, blank=True)
    sku = models.CharField(max_length=50, unique=True, null=True, blank=True)
    brand = models.CharField(max_length=100, blank=True)
    category = models.ForeignKey(ProductCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')

    # Copy
    summary = models.CharField(max_length=300)
    description = models.TextField(blank=True)

    # Pricing
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Leave blank to show 'Contact for pricing'")
    compare_at_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Optional 'was' price shown struck through")
    currency = models.CharField(max_length=3, default='NGN')
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Internal cost basis — staff-only, never shown publicly")

    # Inventory
    track_inventory = models.BooleanField(default=True, help_text="Uncheck for made-to-order/unlimited products")
    stock_quantity = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(null=True, blank=True)

    # Physical attributes
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default='new')
    warranty_months = models.PositiveIntegerField(null=True, blank=True)
    weight_kg = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    length_cm = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    width_cm = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    height_cm = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    # Status
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'eduweb_product'
        verbose_name = 'Product'
        verbose_name_plural = 'Store Products'
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    @property
    def is_in_stock(self):
        return (not self.track_inventory) or self.stock_quantity > 0

    @property
    def is_low_stock(self):
        """Whether to show a 'Only N left' nudge. Falls back to a default
        threshold of 10 when staff haven't set low_stock_threshold, so the
        UI still works out of the box on products that never had it set."""
        if not self.track_inventory or self.stock_quantity <= 0:
            return False
        threshold = self.low_stock_threshold if self.low_stock_threshold is not None else 10
        return self.stock_quantity <= threshold

    @property
    def primary_image(self):
        return self.images.filter(is_primary=True).first() or self.images.first()


class ProductSpecification(models.Model):
    """One row of an Amazon-style key/value 'Technical Details' table."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='specifications')
    label = models.CharField(max_length=100)
    value = models.CharField(max_length=300)
    sort_order = models.PositiveIntegerField(default=0, blank=True)

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self):
        return f"{self.product.title} — {self.label}: {self.value}"


class ProductVariant(models.Model):
    """A selectable option for a product — e.g. Size: Large, Color: Red.
    Picked at Add to Cart time; the chosen value is snapshotted onto the
    OrderItem as `variant_label` so a later catalog edit never changes what
    a historical order says was bought."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    option_name = models.CharField(max_length=50, default='Size', help_text="e.g. 'Size' or 'Color'")
    value = models.CharField(max_length=50, help_text="e.g. 'Large' or 'Red'")
    sort_order = models.PositiveIntegerField(default=0, blank=True)

    class Meta:
        ordering = ['option_name', 'sort_order', 'id']

    def __str__(self):
        return f"{self.product.title} — {self.option_name}: {self.value}"


class MediaAsset(models.Model):
    """Shared upload pool — the same file can be attached to more than one
    product's gallery without re-uploading it."""
    file = models.ImageField(upload_to='store/media/')
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return self.file.name.rsplit('/', 1)[-1]


class ProductImage(models.Model):
    """One gallery image for a product, pointing at a reusable MediaAsset."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    asset = models.ForeignKey(MediaAsset, on_delete=models.CASCADE, related_name='product_links')
    sort_order = models.PositiveIntegerField(default=0)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self):
        return f"{self.product.title} image #{self.sort_order}"


class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending Payment'),
        ('paid', 'Paid — Pending Fulfillment'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped — In Transit'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]

    # The order a paid order moves through — staff can only advance to the
    # next stage from wherever it currently is (see management/order_detail).
    FULFILLMENT_SEQUENCE = ['paid', 'processing', 'shipped', 'delivered']

    # Any status where money actually changed hands and hasn't been
    # returned yet — refunding also doubles as "cancel" here, since a
    # refunded order drops out of FULFILLMENT_SEQUENCE and stops
    # progressing.
    REFUNDABLE_STATUSES = ['paid', 'processing', 'shipped', 'delivered']

    order_number = models.CharField(max_length=20, unique=True, editable=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='store_orders')
    buyer_name = models.CharField(max_length=150)
    buyer_email = models.EmailField()

    # Delivery — required for every order since the catalog sells physical
    # goods. Captured at checkout, snapshotted here (not read from a profile
    # address book, which doesn't exist) so a later account edit never
    # changes where an already-placed order says to deliver.
    delivery_phone = models.CharField(max_length=20, blank=True)
    delivery_address = models.TextField(blank=True)
    delivery_city = models.CharField(max_length=100, blank=True)
    delivery_state = models.CharField(max_length=100, blank=True)

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='NGN')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    payment_reference = models.CharField(max_length=100, unique=True)
    gateway_payment_id = models.CharField(max_length=255, blank=True)
    payment_metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    processing_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    delivered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='store_orders_delivered')
    refunded_at = models.DateTimeField(null=True, blank=True)
    refunded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='store_orders_refunded')
    refund_reason = models.TextField(blank=True, help_text="Staff's note on the refund decision — set whether approved or rejected.")

    REFUND_REQUEST_STATUS_CHOICES = [
        ('none', 'No Request'),
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    refund_request_status = models.CharField(max_length=20, choices=REFUND_REQUEST_STATUS_CHOICES, default='none')
    refund_requested_at = models.DateTimeField(null=True, blank=True)
    refund_request_reason = models.TextField(blank=True, help_text="Customer's stated reason for requesting a cancellation/refund.")
    staff_note = models.TextField(blank=True)

    @property
    def can_be_refunded(self):
        return self.status in self.REFUNDABLE_STATUSES

    def advance_status(self, new_status, user):
        """Move this order to `new_status`, stamping the matching timestamp
        (and delivered_by, for the terminal stage). Only allows moving to
        the next stage in FULFILLMENT_SEQUENCE from wherever it currently
        is — never backwards, never skipping a stage."""
        try:
            current_index = self.FULFILLMENT_SEQUENCE.index(self.status)
        except ValueError:
            raise ValueError(f"Order is '{self.status}', not in the fulfillment pipeline.")
        try:
            target_index = self.FULFILLMENT_SEQUENCE.index(new_status)
        except ValueError:
            raise ValueError(f"'{new_status}' is not a valid fulfillment stage.")
        if target_index != current_index + 1:
            raise ValueError(f"Cannot move from '{self.status}' directly to '{new_status}'.")

        self.status = new_status
        now = timezone.now()
        update_fields = ['status', 'updated_at']
        if new_status == 'processing':
            self.processing_at = now
            update_fields.append('processing_at')
        elif new_status == 'shipped':
            self.shipped_at = now
            update_fields.append('shipped_at')
        elif new_status == 'delivered':
            self.delivered_at = now
            self.delivered_by = user
            update_fields += ['delivered_at', 'delivered_by']
        self.save(update_fields=update_fields)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['payment_reference']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"Order {self.order_number} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = f"ORD-{uuid.uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, related_name='order_items')

    # Snapshotted at purchase time so a later catalog edit (or product
    # deletion) never changes what a historical order says it charged.
    product_title = models.CharField(max_length=150)
    variant_label = models.CharField(max_length=100, blank=True, help_text="e.g. 'Size: Large'")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='NGN')
    quantity = models.PositiveIntegerField(default=1)

    @property
    def line_total(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.product_title} x{self.quantity}"
