from rest_framework import serializers
from .models import DietPlanPDF


class DietPlanPDFSerializer(serializers.ModelSerializer):

    class Meta:
        model = DietPlanPDF
        fields = [
            "id",
            "member",
            "pdf",
            "created_at"
        ]