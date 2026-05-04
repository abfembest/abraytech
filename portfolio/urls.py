# portfolio/urls.py
from django.urls import path, re_path
from . import views

app_name = 'portfolio'

urlpatterns = [
    re_path(r'^project/(?P<slug>[\w-]+)?/?$', views.project_detail_or_selector, name='project_detail'),
    path('api/project/<slug:slug>/', views.project_api_data, name='project_api_data'),
]