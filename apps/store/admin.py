from django.contrib import admin

from .models import Order, Product, ProductCategory


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
