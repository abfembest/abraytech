from django.urls import path

from . import views

app_name = 'store'

urlpatterns = [
    path('', views.store_list, name='store_list'),
    path('cart/', views.cart_view, name='cart_view'),
    path('cart/add/', views.cart_add, name='cart_add'),
    path('checkout/', views.checkout_view, name='checkout_view'),
    path('checkout/login/', views.store_login, name='store_login'),
    path('checkout/forgot-password/', views.forgot_password, name='forgot_password'),
    path('checkout/reset-password/<uuid:token>/', views.reset_password, name='reset_password'),
    path('checkout/callback/', views.checkout_callback, name='checkout_callback'),
    path('paystack/webhook/', views.paystack_webhook, name='paystack_webhook'),
    path('orders/', views.my_orders, name='my_orders'),
    path('orders/<str:order_number>/refund-request/', views.request_refund, name='request_refund'),
    path('orders/<str:order_number>/return/', views.return_request_new, name='return_request_new'),
    path('account/', views.store_profile, name='store_profile'),
    path('<slug:slug>/', views.product_detail, name='product_detail'),
]
