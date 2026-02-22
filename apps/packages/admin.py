from django.contrib import admin
from .models import SavedPackage


@admin.register(SavedPackage)
class SavedPackageAdmin(admin.ModelAdmin):
    list_display = ['label', 'user', 'length', 'width', 'height', 'weight_lb', 'weight_oz']
    search_fields = ['label']
    readonly_fields = ['created_at', 'updated_at']