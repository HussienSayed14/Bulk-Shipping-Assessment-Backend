from django.db import models
from django.contrib.auth.models import User


class ShipmentBatch(models.Model):
    """
    Represents one CSV upload session.
    Groups all shipment records from a single file upload.
    """

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'                              # just uploaded
        REVIEWED = 'reviewed', 'Reviewed'                      # user finished step 2
        SHIPPING_SELECTED = 'shipping_selected', 'Shipping Selected'  # user finished step 3
        PURCHASED = 'purchased', 'Purchased'                   # payment completed

    class LabelSize(models.TextChoices):
        LETTER = 'letter', 'Letter / A4 (8.5x11)'
        THERMAL = '4x6', '4x6 inch (Thermal)'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='batches')
    file_name = models.CharField(max_length=255, help_text='Original uploaded CSV filename')
    total_records = models.IntegerField(default=0)
    valid_records = models.IntegerField(default=0)
    invalid_records = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    label_size = models.CharField(max_length=10, choices=LabelSize.choices, blank=True, default='')
    total_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.00) # type: ignore
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'shipment_batches'
        verbose_name = 'Shipment Batch'
        verbose_name_plural = 'Shipment Batches'
        ordering = ['-created_at']

    def __str__(self):
        return f"Batch #{self.pk} - {self.file_name} ({self.total_records} records)"

    def recalculate_stats(self):
        """Recalculate valid/invalid counts and total cost from child records."""
        records = self.records.all() # type: ignore
        self.total_records = records.count()
        self.valid_records = records.filter(is_valid=True).count()
        self.invalid_records = records.filter(is_valid=False).count()
        self.total_cost = sum(
            r.shipping_cost for r in records if r.shipping_cost
        )
        self.save(update_fields=['total_records', 'valid_records', 'invalid_records', 'total_cost', 'updated_at'])


class ShipmentRecord(models.Model):
    """
    Represents a single shipment row parsed from the CSV.
    Contains sender, recipient, package details, and shipping selection.
    """

    class VerificationStatus(models.TextChoices):
        UNVERIFIED = 'unverified', 'Unverified'
        VERIFIED = 'verified', 'Verified'
        FAILED = 'failed', 'Failed'

    class ShippingService(models.TextChoices):
        PRIORITY = 'priority', 'Priority Mail'
        GROUND = 'ground', 'Ground Shipping'

    batch = models.ForeignKey(ShipmentBatch, on_delete=models.CASCADE, related_name='records')
    row_number = models.IntegerField(help_text='Original row number in CSV')

    # ── Ship From ──
    from_first_name = models.CharField(max_length=100, blank=True, default='')
    from_last_name = models.CharField(max_length=100, blank=True, default='')
    from_address1 = models.CharField(max_length=255, blank=True, default='')
    from_address2 = models.CharField(max_length=255, blank=True, default='')
    from_city = models.CharField(max_length=100, blank=True, default='')
    from_state = models.CharField(max_length=2, blank=True, default='')
    from_zip = models.CharField(max_length=10, blank=True, default='')
    from_phone = models.CharField(max_length=20, blank=True, default='')

    # ── Ship To ──
    to_first_name = models.CharField(max_length=100, blank=True, default='')
    to_last_name = models.CharField(max_length=100, blank=True, default='')
    to_address1 = models.CharField(max_length=255, blank=True, default='')
    to_address2 = models.CharField(max_length=255, blank=True, default='')
    to_city = models.CharField(max_length=100, blank=True, default='')
    to_state = models.CharField(max_length=2, blank=True, default='')
    to_zip = models.CharField(max_length=10, blank=True, default='')
    to_phone = models.CharField(max_length=20, blank=True, default='')

    # ── Package Details ──
    weight_lb = models.IntegerField(null=True, blank=True)
    weight_oz = models.IntegerField(null=True, blank=True)
    length = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    width = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    height = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    # ── Reference ──
    order_number = models.CharField(max_length=100, blank=True, default='')
    item_sku = models.CharField(max_length=100, blank=True, default='')

    # ── Validation ──
    validation_errors = models.JSONField(default=list, blank=True)
    is_valid = models.BooleanField(default=False)

    # ── Address Verification ──
    from_address_verified = models.CharField(
        max_length=12,
        choices=VerificationStatus.choices,
        default=VerificationStatus.UNVERIFIED,
    )
    to_address_verified = models.CharField(
        max_length=12,
        choices=VerificationStatus.choices,
        default=VerificationStatus.UNVERIFIED,
    )

    # ── Shipping ──
    shipping_service = models.CharField(
        max_length=10,
        choices=ShippingService.choices,
        blank=True,
        default='',
    )
    shipping_cost = models.DecimalField(max_digits=8, decimal_places=2, default=0.00) # type: ignore

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'shipment_records'
        verbose_name = 'Shipment Record'
        verbose_name_plural = 'Shipment Records'
        ordering = ['row_number']

    def __str__(self):
        return f"Row {self.row_number} - {self.to_first_name} {self.to_last_name} ({self.order_number})"

    @property
    def total_weight_oz(self):
        """Total weight in ounces for rate calculation."""
        lb = self.weight_lb or 0
        oz = self.weight_oz or 0
        return (lb * 16) + oz

    @property
    def from_address_display(self):
        """Formatted ship-from address for table display."""
        parts = [
            f"{self.from_first_name} {self.from_last_name}".strip(),
            self.from_address1,
            self.from_address2,
            f"{self.from_city}, {self.from_state} {self.from_zip}".strip(', '),
        ]
        return '\n'.join(p for p in parts if p)

    @property
    def to_address_display(self):
        """Formatted ship-to address for table display."""
        parts = [
            f"{self.to_first_name} {self.to_last_name}".strip(),
            self.to_address1,
            self.to_address2,
            f"{self.to_city}, {self.to_state} {self.to_zip}".strip(', '),
        ]
        return '\n'.join(p for p in parts if p)

    @property
    def package_display(self):
        """Formatted package details for table display."""
        dims = ''
        if self.length and self.width and self.height:
            dims = f"{self.length}x{self.width}x{self.height} in"

        weight = ''
        if self.weight_lb or self.weight_oz:
            lb = self.weight_lb or 0
            oz = self.weight_oz or 0
            weight = f"{lb}lb {oz}oz"

        if dims and weight:
            return f"{dims} / {weight}"
        return dims or weight or 'No package info'