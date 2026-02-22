from django.db import models
from django.contrib.auth.models import User


class Transaction(models.Model):
    """
    Records all financial transactions — purchases, refunds, top-ups.
    Used for the billing page and order history.
    """

    class Type(models.TextChoices):
        PURCHASE = 'purchase', 'Purchase'
        REFUND = 'refund', 'Refund'
        TOPUP = 'topup', 'Top Up'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    batch = models.ForeignKey(
        'shipments.ShipmentBatch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions',
    )
    type = models.CharField(max_length=10, choices=Type.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.CharField(max_length=500, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'transactions'
        verbose_name = 'Transaction'
        verbose_name_plural = 'Transactions'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_type_display()} - ${self.amount} ({self.user.username})" # type: ignore