from django.urls import path
from . import views

urlpatterns = [
    path('saved-addresses/', views.address_list, name='address-list'),
    path('saved-addresses/create/', views.address_create, name='address-create'),
    path('saved-addresses/<int:address_id>/', views.address_detail, name='address-detail'),
    path('saved-addresses/<int:address_id>/update/', views.address_update, name='address-update'),
    path('saved-addresses/<int:address_id>/delete/', views.address_delete, name='address-delete'),
]