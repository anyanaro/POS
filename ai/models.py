# ai/models.py
from django.db import models
from django.conf import settings


class ModelRun(models.Model):
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    params = models.JSONField(default=dict)
    metrics = models.JSONField(default=dict)
    status = models.CharField(max_length=32, default="running")
    model_name = models.CharField(max_length=64, default="prophet")

# ai/models.py (optional)
class FeatureSnapshot(models.Model):
    entity_type = models.CharField(max_length=32)  # 'txn'|'sku_branch'|...
    entity_id = models.CharField(max_length=64)
    as_of = models.DateTimeField()
    features = models.JSONField(default=dict)
    label = models.FloatField(null=True, blank=True)
    split = models.CharField(max_length=16, default="train")  # 'train'|'valid'|'prod'


class Forecast(models.Model):
    date = models.DateField(db_index=True)
    branch = models.ForeignKey('accounts.Branch', on_delete=models.CASCADE)
    product = models.ForeignKey('accounts.Product', on_delete=models.CASCADE)
    yhat = models.FloatField()
    yhat_lower = models.FloatField()
    yhat_upper = models.FloatField()
    model_version = models.CharField(max_length=64, default="seasonal-naive-v1")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("date", "branch", "product", "model_version")

    def __str__(self):
        return f"{self.date} {self.branch_id} {self.product_id} {self.yhat:.2f}"