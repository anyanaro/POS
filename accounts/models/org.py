# accounts/models/org.py
from django.db import models
from django.contrib.auth.models import User

class Branch(models.Model):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=150)
    address = models.TextField(blank=True, null=True)
    active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Branches"

    def __str__(self):
        return f"{self.code} - {self.name}"

class UserBranch(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="branch_links")
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    is_default = models.BooleanField(default=False)

    class Meta:
        unique_together = ("user", "branch")