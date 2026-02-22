from django.urls import path
from . import views

urlpatterns = [
    # Batch endpoints
    path('batches/', views.batch_list, name='batch-list'),
    path('batches/upload/', views.upload_csv, name='batch-upload'),
    path('batches/<int:batch_id>/', views.batch_detail, name='batch-detail'),
    path('batches/<int:batch_id>/delete/', views.batch_delete, name='batch-delete'),

    # Shipment record endpoints
    path('batches/<int:batch_id>/shipments/', views.shipment_list, name='shipment-list'),
    path('shipments/<int:shipment_id>/', views.shipment_detail, name='shipment-detail'),
    path('shipments/<int:shipment_id>/update/', views.shipment_update, name='shipment-update'),
    path('shipments/<int:shipment_id>/delete/', views.shipment_delete, name='shipment-delete'),

    # Bulk actions
    path('batches/<int:batch_id>/shipments/bulk-update-from/', views.bulk_update_from_address, name='bulk-update-from'),
    path('batches/<int:batch_id>/shipments/bulk-update-package/', views.bulk_update_package, name='bulk-update-package'),
    path('batches/<int:batch_id>/shipments/bulk-update-shipping/', views.bulk_update_shipping, name='bulk-update-shipping'),
    path('batches/<int:batch_id>/shipments/bulk-delete/', views.bulk_delete, name='bulk-delete'),

    # Shipping rates
    path('shipping-rates/', views.shipping_rates, name='shipping-rates'),
    path('batches/<int:batch_id>/calculate-rates/', views.calculate_batch_rates, name='calculate-rates'),

    # Purchase
    path('batches/<int:batch_id>/purchase/', views.purchase_batch, name='batch-purchase'),
]