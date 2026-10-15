from rest_framework import serializers
from .models import GymEquipment


class GymEquipmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = GymEquipment
        fields = [
            "id",
            "name",
            "quantity",
            "weight",
            "is_available",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
        ]


from .models import BiometricEmployeeMapping


class BiometricEmployeeMappingSerializer(serializers.ModelSerializer):
    member_name = serializers.CharField(
        source="member.name",
        read_only=True,
        default=None,
    )
    staff_name = serializers.CharField(
        source="staff.name",
        read_only=True,
        default=None,
    )

    class Meta:
        model = BiometricEmployeeMapping
        fields = [
            "id",
            "essl_employee_code",
            "essl_employee_name",
            "member",
            "member_name",
            "staff",
            "staff_name",
            "is_active",
            "last_synced_at",
        ]
        read_only_fields = [
            "id",
            "essl_employee_code",
            "essl_employee_name",
            "member_name",
            "staff_name",
            "last_synced_at",
        ]