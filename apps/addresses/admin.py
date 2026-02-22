from django.contrib import admin
from .models import SavedAddress


@admin.register(SavedAddress)
class SavedAddressAdmin(admin.ModelAdmin):
    list_display = ['label', 'user', 'address_line1', 'city', 'state', 'zip_code', 'is_default']
    list_filter = ['state', 'is_default']
    search_fields = ['label', 'address_line1', 'city']
    readonly_fields = ['created_at', 'updated_at']