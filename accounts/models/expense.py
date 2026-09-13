# accounts/models/expense.py
from django.db import models
from django.contrib.auth.models import User
from .org import Branch

class Expense(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    date = models.DateField()
    category = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)