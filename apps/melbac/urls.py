from django.urls import path
from . import views

app_name = 'melbac'

urlpatterns = [
    path('',                    views.index,        name='index'),
    path('about/',              views.about,         name='about'),
    path('academics/',          views.academics,     name='academics'),
    path('admissions/',         views.admissions,    name='admissions'),
    path('activities/',         views.activities,    name='activities'),
    path('contact/',            views.contact,       name='contact'),
    path('blog/',               views.blog_list,     name='blog'),
    path('blog/<slug:slug>/',   views.blog_detail,   name='blog_detail'),
]