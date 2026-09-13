# ai/views.py
from rest_framework import viewsets, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from ai.models import Forecast
from ai.serializers import ForecastSerializer
from ai.services.forecasting import forecast_sku_branch, persist_forecasts

class ForecastViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Forecast.objects.all().order_by("-date")
    serializer_class = ForecastSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if "branch_id" in params: qs = qs.filter(branch_id=params["branch_id"])
        if "product_id" in params: qs = qs.filter(product_id=params["product_id"])
        if "from" in params: qs = qs.filter(date__gte=params["from"])
        if "to" in params: qs = qs.filter(date__lte=params["to"])
        return qs

    @action(detail=False, methods=["post"], url_path="generate")
    def generate(self, request):
        branch_id = request.data.get("branch_id")
        product_id = request.data.get("product_id")
        horizon = int(request.data.get("horizon_days", 28))
        if not branch_id or not product_id:
            return Response({"detail": "branch_id and product_id are required."}, status=400)
        horizon = max(1, min(horizon, 90))
        predictions, model_version = forecast_sku_branch(
            int(branch_id), int(product_id), horizon_days=horizon
        )
        created = persist_forecasts(int(branch_id), int(product_id), predictions, model_version)
        return Response({
            "model_version": model_version,
            "created": created,
            "predictions": predictions,
        })