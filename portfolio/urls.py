# portfolio/urls.py
from django.urls import path
from . import views

app_name = 'portfolio'

urlpatterns = [
    path('project/<slug:slug>/', views.project_detail, name='project_detail'),
    path('api/project/<slug:slug>/', views.project_api_data, name='project_api_data'),
]