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

from .models import Exercises


from rest_framework import serializers

from .models import Exercises


class ExerciseSerializer(serializers.ModelSerializer):

    class Meta:

        model = Exercises

        fields = [
            "id",
            "name",
            "body_part",
            "equipment",
            "image",
        ]

from .models import GymEquipment


class GymEquipmentSerializer(serializers.ModelSerializer):

    class Meta:
        model = GymEquipment
        fields = [
            "id",
            "name",
            "quantity",
            "is_available",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]