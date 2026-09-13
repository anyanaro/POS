# ai/serializers.py
from rest_framework import serializers
from ai.models import Forecast

class ForecastSerializer(serializers.ModelSerializer):
    class Meta:
        model = Forecast
        fields = "__all__"
