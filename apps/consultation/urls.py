from django.urls import path

from . import views

app_name = 'consultation'

urlpatterns = [
    path('', views.book_consultation, name='book_consultation'),
    path('callback/', views.booking_callback, name='booking_callback'),
    path('paystack/webhook/', views.paystack_webhook, name='paystack_webhook'),
]
