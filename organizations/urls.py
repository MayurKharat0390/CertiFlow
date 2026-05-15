from django.urls import path
from . import views

app_name = 'organizations'

urlpatterns = [
    path('', views.organization_list, name='org_list'),
    path('<slug:slug>/', views.organization_detail, name='org_detail'),
]
