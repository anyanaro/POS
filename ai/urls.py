# ai/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from ai.views import ForecastViewSet

router = DefaultRouter()
router.register(r"forecasts", ForecastViewSet, basename="ai-forecasts")

urlpatterns = [ path("", include(router.urls)), ]