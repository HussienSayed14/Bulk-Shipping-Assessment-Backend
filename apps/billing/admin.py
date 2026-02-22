from django.contrib import admin
from .models import Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'type', 'amount', 'description', 'created_at']
    list_filter = ['type', 'created_at']
    search_fields = ['user__username', 'description']
    readonly_fields = ['created_at']