from django.db import models
from django.contrib.auth.models import User


class SavedPackage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_packages')
    label = models.CharField(max_length=100, help_text='e.g. Light Package, Standard Box')
    length = models.DecimalField(max_digits=6, decimal_places=2, help_text='Length in inches')
    width = models.DecimalField(max_digits=6, decimal_places=2, help_text='Width in inches')
    height = models.DecimalField(max_digits=6, decimal_places=2, help_text='Height in inches')
    weight_lb = models.IntegerField(default=0, help_text='Weight in pounds')
    weight_oz = models.IntegerField(default=0, help_text='Weight in ounces')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'saved_packages'
        verbose_name = 'Saved Package'
        verbose_name_plural = 'Saved Packages'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.label} - {self.length}x{self.width}x{self.height} ({self.weight_lb}lb {self.weight_oz}oz)"

    @property
    def total_weight_oz(self):
        """Total weight in ounces for rate calculation."""
        return (self.weight_lb * 16) + self.weight_oz