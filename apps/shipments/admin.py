from django.contrib import admin
from .models import ShipmentBatch, ShipmentRecord


@admin.register(ShipmentBatch)
class ShipmentBatchAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'file_name', 'total_records', 'valid_records',
                    'invalid_records', 'status', 'total_cost', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['file_name', 'user__username']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(ShipmentRecord)
class ShipmentRecordAdmin(admin.ModelAdmin):
    list_display = ['id', 'batch', 'row_number', 'to_first_name', 'to_last_name',
                    'to_city', 'to_state', 'is_valid', 'to_address_verified',
                    'shipping_service', 'shipping_cost']
    list_filter = ['is_valid', 'to_address_verified', 'from_address_verified',
                   'shipping_service', 'batch']
    search_fields = ['to_first_name', 'to_last_name', 'to_address1',
                     'order_number', 'item_sku']
    readonly_fields = ['created_at', 'updated_at']