from rest_framework import serializers
from .models import SavedPackage


class SavedPackageSerializer(serializers.ModelSerializer):
    total_weight_oz = serializers.IntegerField(read_only=True)

    class Meta:
        model = SavedPackage
        fields = [
            'id', 'label', 'length', 'width', 'height',
            'weight_lb', 'weight_oz', 'total_weight_oz',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'total_weight_oz', 'created_at', 'updated_at']

    def validate_length(self, value):
        if value <= 0:
            raise serializers.ValidationError('Length must be greater than 0.')
        return value

    def validate_width(self, value):
        if value <= 0:
            raise serializers.ValidationError('Width must be greater than 0.')
        return value

    def validate_height(self, value):
        if value <= 0:
            raise serializers.ValidationError('Height must be greater than 0.')
        return value

    def validate(self, data):
        weight_lb = data.get('weight_lb', getattr(self.instance, 'weight_lb', 0) if self.instance else 0)
        weight_oz = data.get('weight_oz', getattr(self.instance, 'weight_oz', 0) if self.instance else 0)

        if (weight_lb or 0) <= 0 and (weight_oz or 0) <= 0:
            raise serializers.ValidationError('Package must have weight (lbs or oz must be greater than 0).')

        if (weight_lb or 0) < 0:
            raise serializers.ValidationError({'weight_lb': 'Weight cannot be negative.'})
        if (weight_oz or 0) < 0:
            raise serializers.ValidationError({'weight_oz': 'Weight cannot be negative.'})

        return data