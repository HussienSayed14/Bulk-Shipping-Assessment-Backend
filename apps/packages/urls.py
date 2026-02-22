from django.urls import path
from . import views

urlpatterns = [
    path('saved-packages/', views.package_list, name='package-list'),
    path('saved-packages/create/', views.package_create, name='package-create'),
    path('saved-packages/<int:package_id>/', views.package_detail, name='package-detail'),
    path('saved-packages/<int:package_id>/update/', views.package_update, name='package-update'),
    path('saved-packages/<int:package_id>/delete/', views.package_delete, name='package-delete'),
]