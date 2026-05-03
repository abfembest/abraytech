from django.urls import path
from . import views
app_name = "chatbot"
urlpatterns = [
    path('', views.index, name='chatbot_ui'),
    path('api/chat/start/', views.start_session, name='start_session'),
    path('api/chat/message/', views.send_message, name='send_message'),
    path('api/chat/close/', views.close_session, name='close_session'),
    path('api/chat/session/', views.session_status, name='session_status'),
]