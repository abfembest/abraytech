from django.urls import path
from . import views

app_name = 'library'

urlpatterns = [
    # Home — /library/
    path('', views.home, name='home'),

    # Global search — /library/search/
    path('search/', views.search, name='search'),

    # Category list — /library/books/  /library/periodicals/ etc.
    path('<slug:category_slug>/', views.category, name='category'),

    # Item detail — /library/item/<slug>/
    path('item/<slug:slug>/', views.detail, name='detail'),

    # Download — /library/item/<slug>/download/
    path('item/<slug:slug>/download/', views.download, name='download'),
]