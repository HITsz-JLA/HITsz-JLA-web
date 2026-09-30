from django.urls import path
from . import views

urlpatterns = [
    path('csrf/', views.csrf, name='community-csrf'),
    path('health/', views.health, name='community-health'),
    path('submissions/<str:kind>/', views.submit, name='community-submit'),
    path('feedback/', views.feedback_list, name='community-feedback'),
]
