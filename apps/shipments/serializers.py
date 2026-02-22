from rest_framework import serializers
from .models import ShipmentBatch, ShipmentRecord


# =============================================================================
# SHIPMENT RECORD SERIALIZERS
# =============================================================================

class ShipmentRecordSerializer(serializers.ModelSerializer):
    """Full serializer for shipment records with computed display fields."""

    from_address_display = serializers.CharField(read_only=True)
    to_address_display = serializers.CharField(read_only=True)
    package_display = serializers.CharField(read_only=True)
    total_weight_oz = serializers.IntegerField(read_only=True)

    class Meta:
        model = ShipmentRecord
        fields = [
            'id', 'batch', 'row_number',
            # Ship From
            'from_first_name', 'from_last_name', 'from_address1', 'from_address2',
            'from_city', 'from_state', 'from_zip', 'from_phone',
            # Ship To
            'to_first_name', 'to_last_name', 'to_address1', 'to_address2',
            'to_city', 'to_state', 'to_zip', 'to_phone',
            # Package
            'weight_lb', 'weight_oz', 'length', 'width', 'height',
            # Reference
            'order_number', 'item_sku',
            # Validation
            'validation_errors', 'is_valid',
            # Verification
            'from_address_verified', 'to_address_verified',
            # Shipping
            'shipping_service', 'shipping_cost',
            # Display fields
            'from_address_display', 'to_address_display', 'package_display',
            'total_weight_oz',
            # Timestamps
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'batch', 'row_number', 'validation_errors', 'is_valid',
            'from_address_verified', 'to_address_verified',
            'shipping_cost', 'created_at', 'updated_at',
        ]


class ShipmentRecordUpdateSerializer(serializers.ModelSerializer):
    """Serializer for editing a single shipment record."""

    class Meta:
        model = ShipmentRecord
        fields = [
            # Ship From
            'from_first_name', 'from_last_name', 'from_address1', 'from_address2',
            'from_city', 'from_state', 'from_zip', 'from_phone',
            # Ship To
            'to_first_name', 'to_last_name', 'to_address1', 'to_address2',
            'to_city', 'to_state', 'to_zip', 'to_phone',
            # Package
            'weight_lb', 'weight_oz', 'length', 'width', 'height',
            # Reference
            'order_number', 'item_sku',
            # Shipping
            'shipping_service',
        ]


# =============================================================================
# SHIPMENT BATCH SERIALIZERS
# =============================================================================

class ShipmentBatchSerializer(serializers.ModelSerializer):
    """Full serializer for batch details."""

    class Meta:
        model = ShipmentBatch
        fields = [
            'id', 'file_name', 'total_records', 'valid_records',
            'invalid_records', 'status', 'label_size', 'total_cost',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields


class ShipmentBatchListSerializer(serializers.ModelSerializer):
    """Lighter serializer for listing batches."""

    class Meta:
        model = ShipmentBatch
        fields = [
            'id', 'file_name', 'total_records', 'valid_records',
            'invalid_records', 'status', 'total_cost', 'created_at',
        ]
        read_only_fields = fields


# =============================================================================
# UPLOAD SERIALIZER
# =============================================================================

class CSVUploadSerializer(serializers.Serializer):
    """Serializer for CSV file upload."""
    file = serializers.FileField(
        help_text='CSV file following the template format',
    )

    def validate_file(self, value):
        # Check file extension
        if not value.name.lower().endswith('.csv'):
            raise serializers.ValidationError('Only CSV files are allowed.')

        # Check file size (10MB max)
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError('File size cannot exceed 10MB.')

        # Check file is not empty
        if value.size == 0:
            raise serializers.ValidationError('File is empty.')

        return value


# =============================================================================
# BULK ACTION SERIALIZERS
# =============================================================================

class BulkShipmentIdsSerializer(serializers.Serializer):
    """Base serializer for bulk actions that need shipment IDs."""
    shipment_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        help_text='List of shipment record IDs',
    )


class BulkUpdateFromAddressSerializer(BulkShipmentIdsSerializer):
    """Bulk update ship-from address using a saved address."""
    saved_address_id = serializers.IntegerField(
        help_text='ID of the saved address to apply',
    )


class BulkUpdatePackageSerializer(BulkShipmentIdsSerializer):
    """Bulk update package details using a saved package."""
    saved_package_id = serializers.IntegerField(
        help_text='ID of the saved package preset to apply',
    )


class BulkUpdateShippingSerializer(BulkShipmentIdsSerializer):
    """Bulk update shipping service."""
    service = serializers.ChoiceField(
        choices=['priority', 'ground', 'cheapest'],
        help_text='"priority", "ground", or "cheapest" for most affordable',
    )


class BulkDeleteSerializer(BulkShipmentIdsSerializer):
    """Bulk delete shipment records."""
    pass


# =============================================================================
# PURCHASE SERIALIZER
# =============================================================================

class PurchaseSerializer(serializers.Serializer):
    """Serializer for the final purchase step."""
    label_size = serializers.ChoiceField(
        choices=['letter', '4x6'],
        help_text='"letter" for A4/Letter or "4x6" for thermal labels',
    )
    accept_terms = serializers.BooleanField(
        help_text='Must be true to proceed with purchase',
    )

    def validate_accept_terms(self, value):
        if not value:
            raise serializers.ValidationError('You must accept the terms to proceed.')
        return value


class PurchaseResponseSerializer(serializers.Serializer):
    """Response serializer for Swagger documentation."""
    message = serializers.CharField()
    batch_id = serializers.IntegerField()
    total_labels = serializers.IntegerField()
    total_cost = serializers.DecimalField(max_digits=10, decimal_places=2)
    label_size = serializers.CharField()
    new_balance = serializers.DecimalField(max_digits=10, decimal_places=2)