from django.urls import path

from . import views

app_name = 'marketing'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),

    path('leads/', views.lead_list, name='lead_list'),
    path('leads/create/', views.lead_create, name='lead_create'),
    path('leads/<int:pk>/edit/', views.lead_edit, name='lead_edit'),
    path('leads/<int:pk>/', views.lead_detail, name='lead_detail'),

    path('chat/', views.chat, name='chat'),
    path('chat/all/', views.chat_list, name='chat_list'),
    path('chat/messages/', views.chat_messages, name='chat_messages'),
    path('chat/send/', views.chat_send, name='chat_send'),
]
