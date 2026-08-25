from django.contrib import admin

from .models import Order, Product, ProductCategory, ReturnItem, ReturnRequest


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'icon')
    search_fields = ('title', 'slug')
    prepopulated_fields = {'slug': ('title',)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('title', 'sku', 'category', 'price', 'stock_quantity', 'is_active', 'is_featured', 'created_at')
    list_filter = ('is_active', 'is_featured', 'condition', 'category')
    search_fields = ('title', 'sku', 'brand')
    prepopulated_fields = {'slug': ('title',)}


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'buyer_name', 'buyer_email', 'amount', 'currency', 'status', 'created_at')
    list_filter = ('status', 'currency')
    search_fields = ('order_number', 'buyer_name', 'buyer_email', 'payment_reference')


class ReturnItemInline(admin.TabularInline):
    model = ReturnItem
    extra = 0
    readonly_fields = ('order_item', 'reason', 'reason_details', 'decided_by', 'received_by', 'refund_amount')


@admin.register(ReturnRequest)
class ReturnRequestAdmin(admin.ModelAdmin):
    list_display = ('return_number', 'order', 'user', 'condition_confirmed', 'requested_at')
    search_fields = ('return_number', 'order__order_number', 'user__email')
    inlines = [ReturnItemInline]


@admin.register(ReturnItem)
class ReturnItemAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'return_request', 'status', 'reason', 'decided_at', 'received_at', 'refunded_at')
    list_filter = ('status', 'reason')
    search_fields = ('return_request__return_number', 'order_item__product_title', 'order_item__order__order_number')
