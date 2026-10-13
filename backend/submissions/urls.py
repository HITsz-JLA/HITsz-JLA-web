from django.urls import path
from . import views
from .visits import record_visit

urlpatterns = [
    path('visits/', record_visit, name='community-visit'),
    path('csrf/', views.csrf, name='community-csrf'),
    path('health/', views.health, name='community-health'),
    path('submissions/<str:kind>/', views.submit, name='community-submit'),
    path('feedback/', views.feedback_list, name='community-feedback'),
]
