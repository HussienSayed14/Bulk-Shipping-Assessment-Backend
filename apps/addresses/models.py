from django.db import models
from django.contrib.auth.models import User


class SavedAddress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_addresses')
    label = models.CharField(max_length=100, help_text='e.g. Main Office, Warehouse A')
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True, default='')
    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255, blank=True, default='')
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2, help_text='2-letter US state abbreviation')
    zip_code = models.CharField(max_length=10)
    phone = models.CharField(max_length=20, blank=True, default='')
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'saved_addresses'
        verbose_name = 'Saved Address'
        verbose_name_plural = 'Saved Addresses'
        ordering = ['-is_default', '-created_at']

    def __str__(self):
        return f"{self.label} - {self.address_line1}, {self.city}, {self.state}"

    def save(self, *args, **kwargs):
        """If this address is set as default, unset all other defaults for this user."""
        if self.is_default:
            SavedAddress.objects.filter(
                user=self.user, is_default=True
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)