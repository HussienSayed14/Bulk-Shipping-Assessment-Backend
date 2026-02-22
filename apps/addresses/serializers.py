from rest_framework import serializers
from .models import SavedAddress


class SavedAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedAddress
        fields = [
            'id', 'label', 'first_name', 'last_name',
            'address_line1', 'address_line2', 'city', 'state',
            'zip_code', 'phone', 'is_default',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_state(self, value):
        from apps.shipments.services.validator import VALID_STATES
        value = value.upper().strip()
        if value not in VALID_STATES:
            raise serializers.ValidationError(f'"{value}" is not a valid US state abbreviation.')
        return value

    def validate_zip_code(self, value):
        import re
        value = value.strip()
        if not re.match(r'^\d{5}(-\d{4})?$', value):
            raise serializers.ValidationError('ZIP code must be 5 digits or 5+4 format (e.g., 91773 or 91773-1234).')
        return value