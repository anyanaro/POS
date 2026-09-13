# ai/admin.py
from django.contrib import admin
from ai.models import Forecast, ModelRun

@admin.register(Forecast)
class ForecastAdmin(admin.ModelAdmin):
    list_display = ("date", "branch", "product", "yhat", "model_version")
    list_filter = ("branch", "product", "model_version", "date")
    search_fields = ("product__name", "product__sku")

@admin.register(ModelRun)
class ModelRunAdmin(admin.ModelAdmin):
    list_display = ("id", "model_name", "status", "started_at", "ended_at")
    readonly_fields = ("started_at", "ended_at", "params", "metrics")

