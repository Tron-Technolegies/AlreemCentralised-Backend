import json
from unittest.mock import MagicMock, patch
from decimal import Decimal
from requests.exceptions import ConnectTimeout
from django.utils import timezone

from adminapp.models import Attendance, BiometricDevice
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from adminapp.models import Branch, CustomUser, GymEquipment, Member, Tenant
from adminapp.views import (
    is_dumbbell_equipment,
    normalize_equipment_name,
)


class EsslAttendanceTimeoutTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Timeout Gym",
            slug="timeout-gym",
        )
        self.branch = Branch.objects.create(
            name="Main Branch",
            location="Downtown",
            manager_name="Manager",
            phone="1234567890",
            capacity=100,
            tenant=self.tenant,
        )
        self.user = CustomUser.objects.create_user(
            username="essl_test_user",
            password="testpassword",
            tenant=self.tenant,
            branch=self.branch,
            role="TENANT_ADMIN",
        )
        self.client.force_authenticate(user=self.user)

        self.device = BiometricDevice.objects.create(
            tenant=self.tenant,
            name="uFace302",
            serial_number="TEST-SERIAL-001",
            location="TCR",
            is_attendance_device=True,
            is_active=True,
        )

        # Create an existing attendance record.
        self.existing_attendance = Attendance.objects.create(
            tenant=self.tenant,
            essl_employee_code="1000",
            punch_time=timezone.now(),
            device=self.device,
            punch_type="INOUT",
            raw_data={"original_record": "existing-test-punch"},
        )

    @patch("adminapp.views.call_essl")
    def test_timeout_preserves_existing_attendance(self, mock_call_essl):
        from django.urls import reverse

        mock_call_essl.side_effect = ConnectTimeout(
            "eSSL server is unreachable"
        )

        # Update this name if your URL pattern uses a different name.
        response = self.client.post(
            reverse("sync-essl-attendance"),
            {"log_date": "2026-10-15"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_502_BAD_GATEWAY,
        )

        # The existing record must remain unchanged.
        self.assertEqual(
            Attendance.objects.filter(tenant=self.tenant).count(),
            1,
        )

        self.existing_attendance.refresh_from_db()
        self.assertEqual(
            self.existing_attendance.essl_employee_code,
            "1000",
        )
        self.assertEqual(
            self.existing_attendance.raw_data["original_record"],
            "existing-test-punch",
        )

        mock_call_essl.assert_called_once()

    @patch("adminapp.views.call_essl")
    def test_repeated_sync_does_not_create_duplicate(self, mock_call_essl):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from django.urls import reverse

        log_date = "2030-01-01"
        punch_datetime = "2030-01-01 12:00:00"

        original_record = (
            f"{punch_datetime},1000,uFace302,TCR,INOUT;"
        )

        mock_call_essl.return_value = original_record

        url = reverse("sync-essl-attendance")
        payload = {"log_date": log_date}

        # First sync
        first_response = self.client.post(
            url, payload, format="json"
        )

        self.assertEqual(
            first_response.status_code,
            200,
            first_response.data,
        )

        punch_time = datetime.strptime(
        "2030-01-01 12:00:00",
        "%Y-%m-%d %H:%M:%S",
        ).replace(tzinfo=ZoneInfo("Asia/Kolkata"))
        
        matching_records = Attendance.objects.filter(
            tenant=self.tenant,
            essl_employee_code="1000",
            punch_time = punch_time,
        )

        self.assertEqual(matching_records.count(), 1)

        # Second sync with exactly the same punch
        second_response = self.client.post(
            url, payload, format="json"
        )

        self.assertEqual(
            second_response.status_code,
            200,
            second_response.data,
        )

        # It must not create another record
        self.assertEqual(matching_records.count(), 1)

def make_dummy_workout_plan(name_prefix="Dumbbell Floor Press", sets=3, reps="10-12"):
    return [
        {
            "day": i,
            "body_part": f"Body Part {i}",
            "workouts": [
                {
                    "workout_name": f"{name_prefix} {i}",
                    "sets": sets,
                    "reps": reps,
                    "duration": "8 min",
                },
                {
                    "workout_name": f"Cable Pushdown {i}",
                    "sets": sets,
                    "reps": reps,
                    "duration": "8 min",
                },
            ],
        }
        for i in range(1, 7)
    ]


class WorkoutGenerationTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Alpha Gym", slug="alpha-gym")
        self.branch = Branch.objects.create(
            name="Main Branch",
            location="Downtown",
            manager_name="Manager",
            phone="1234567890",
            capacity=100,
            tenant=self.tenant,
        )
        self.user = CustomUser.objects.create_user(
            username="staff_user",
            password="testpassword",
            tenant=self.tenant,
            branch=self.branch,
            role="TENANT_ADMIN",
        )
        self.client.force_authenticate(user=self.user)

        # Inventory matching requirement 6: 'Dumbells' (5 kg) and 'cables'
        self.dumbbells = GymEquipment.objects.create(
            name="Dumbells",
            quantity=5,
            weight=Decimal("5.00"),
            is_available=True,
            branch=self.branch,
            tenant=self.tenant,
        )
        self.cables = GymEquipment.objects.create(
            name="cables",
            quantity=5,
            is_available=True,
            branch=self.branch,
            tenant=self.tenant,
        )

        self.member = Member.objects.create(
            id="MEMBER_001",
            name="Test Member",
            phone="9876543210",
            tenant=self.tenant,
            branch=self.branch,
            workout_experience_level="",
            current_workout_day=1,
            is_paused=False,
        )

        self.url = reverse("generate_workout")

    # -------------------------------------------------------------
    # 1. Equipment Normalization Tests
    # -------------------------------------------------------------
    def test_equipment_normalization_recognizes_dumbells(self):
        self.assertEqual(normalize_equipment_name("Dumbells"), "Dumbbells")
        self.assertEqual(normalize_equipment_name("dumbell"), "Dumbbells")
        self.assertEqual(normalize_equipment_name("dumbbell"), "Dumbbells")
        self.assertEqual(normalize_equipment_name("cables"), "Cables")
        self.assertTrue(is_dumbbell_equipment("Dumbells"))
        self.assertTrue(is_dumbbell_equipment("dumbell"))
        self.assertTrue(is_dumbbell_equipment("Dumbbell Floor Press"))

    # -------------------------------------------------------------
    # 2. Beginner saved plan + beginner request -> reuse (plan_reused: true)
    # -------------------------------------------------------------
    def test_beginner_saved_plan_and_beginner_request_reuses(self):
        saved_plan = make_dummy_workout_plan("Dumbbell Goblet Squat", sets=2)
        self.member.workout_plan = saved_plan
        self.member.workout_experience_level = "beginner"
        self.member.current_workout_day = 3
        self.member.save()

        with patch("groq.Groq") as mock_groq:
            response = self.client.post(
                self.url,
                {"member_id": self.member.id, "experience_level": "beginner"},
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json()
            self.assertTrue(data["success"])
            self.assertTrue(data["plan_reused"])
            self.assertEqual(data["experience_level"], "beginner")
            self.assertEqual(data["current_workout_day"], 3)
            self.assertEqual(data["workout_plan"], saved_plan)
            # Ensure AI service was never called
            mock_groq.assert_not_called()

        self.member.refresh_from_db()
        self.assertEqual(self.member.current_workout_day, 3)
        self.assertEqual(self.member.workout_experience_level, "beginner")

    # -------------------------------------------------------------
    # 3. Beginner saved plan + advanced request -> generate new (plan_reused: false)
    # -------------------------------------------------------------
    @patch("groq.Groq")
    def test_beginner_saved_plan_and_advanced_request_generates_new_plan(self, mock_groq):
        saved_plan = make_dummy_workout_plan("Dumbbell Beginner Floor Press", sets=2)
        self.member.workout_plan = saved_plan
        self.member.workout_experience_level = "beginner"
        self.member.current_workout_day = 4
        self.member.save()

        new_advanced_plan = make_dummy_workout_plan("Dumbbell Bulgarian Split Squat", sets=4, reps="6-10")
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=json.dumps({"workout_plan": new_advanced_plan})))
        ]
        mock_client.chat.completions.create.return_value = mock_response
        mock_groq.return_value = mock_client

        response = self.client.post(
            self.url,
            {"member_id": self.member.id, "experience_level": "advanced"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertFalse(data["plan_reused"])
        self.assertEqual(data["experience_level"], "advanced")
        self.assertEqual(data["current_workout_day"], 1)
        self.assertEqual(data["workout_plan"], new_advanced_plan)

        # Database must be updated together
        self.member.refresh_from_db()
        self.assertEqual(self.member.workout_experience_level, "advanced")
        self.assertEqual(self.member.current_workout_day, 1)
        self.assertEqual(self.member.workout_plan, new_advanced_plan)

        # Verify AI prompt contained advanced guidelines and equipment weight
        call_args = mock_client.chat.completions.create.call_args[1]
        user_prompt = call_args["messages"][1]["content"]
        self.assertIn("ADVANCED", user_prompt)
        self.assertIn("5.0 kg", user_prompt)
        self.assertIn("Dumbbells", user_prompt)

    # -------------------------------------------------------------
    # 4. Advanced saved plan + beginner request -> generate new (plan_reused: false)
    # -------------------------------------------------------------
    @patch("groq.Groq")
    def test_advanced_saved_plan_and_beginner_request_generates_new_plan(self, mock_groq):
        saved_plan = make_dummy_workout_plan("Dumbbell Advanced Split Squat", sets=4)
        self.member.workout_plan = saved_plan
        self.member.workout_experience_level = "advanced"
        self.member.current_workout_day = 5
        self.member.save()

        new_beginner_plan = make_dummy_workout_plan("Dumbbell Floor Press", sets=2, reps="10-12")
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=json.dumps({"workout_plan": new_beginner_plan})))
        ]
        mock_client.chat.completions.create.return_value = mock_response
        mock_groq.return_value = mock_client

        response = self.client.post(
            self.url,
            {"member_id": self.member.id, "experience_level": "beginner"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertFalse(data["plan_reused"])
        self.assertEqual(data["experience_level"], "beginner")
        self.assertEqual(data["current_workout_day"], 1)
        self.assertEqual(data["workout_plan"], new_beginner_plan)

        self.member.refresh_from_db()
        self.assertEqual(self.member.workout_experience_level, "beginner")
        self.assertEqual(self.member.current_workout_day, 1)
        self.assertEqual(self.member.workout_plan, new_beginner_plan)

    # -------------------------------------------------------------
    # 5. Missing stored experience level -> regenerate rather than reuse
    # -------------------------------------------------------------
    @patch("groq.Groq")
    def test_missing_stored_experience_level_regenerates(self, mock_groq):
        saved_plan = make_dummy_workout_plan("Legacy Plan", sets=3)
        self.member.workout_plan = saved_plan
        self.member.workout_experience_level = ""  # blank after migration
        self.member.current_workout_day = 4
        self.member.save()

        fresh_plan = make_dummy_workout_plan("Dumbbell Floor Press", sets=2)
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=json.dumps({"workout_plan": fresh_plan})))
        ]
        mock_client.chat.completions.create.return_value = mock_response
        mock_groq.return_value = mock_client

        response = self.client.post(
            self.url,
            {"member_id": self.member.id, "experience_level": "beginner"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertFalse(data["plan_reused"])  # NOT reused!
        self.assertEqual(data["experience_level"], "beginner")
        self.assertEqual(data["current_workout_day"], 1)

        self.member.refresh_from_db()
        self.assertEqual(self.member.workout_experience_level, "beginner")
        self.assertEqual(self.member.current_workout_day, 1)

    # -------------------------------------------------------------
    # 6. Unavailable equipment is rejected
    # -------------------------------------------------------------
    @patch("groq.Groq")
    def test_unavailable_equipment_causes_rejection(self, mock_groq):
        # AI returns exercises with barbell / bench (neither is available in inventory)
        plan_with_barbell = [
            {
                "day": i,
                "body_part": "Chest",
                "workouts": [
                    {
                        "workout_name": "Barbell Bench Press",
                        "sets": 3,
                        "reps": "10-12",
                        "duration": "8 min",
                    }
                ],
            }
            for i in range(1, 7)
        ]
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=json.dumps({"workout_plan": plan_with_barbell})))
        ]
        mock_client.chat.completions.create.return_value = mock_response
        mock_groq.return_value = mock_client

        self.member.current_workout_day = 3
        self.member.save()

        response = self.client.post(
            self.url,
            {"member_id": self.member.id, "experience_level": "beginner"},
        )

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertIn("unavailable equipment", response.json()["error"])

        # Member state should not have changed
        self.member.refresh_from_db()
        self.assertEqual(self.member.current_workout_day, 3)

    # -------------------------------------------------------------
    # 7. Paused member restrictions
    # -------------------------------------------------------------
    def test_paused_member_blocked_from_generating_new_plan(self):
        self.member.is_paused = True
        self.member.workout_plan = []
        self.member.save()

        response = self.client.post(
            self.url,
            {"member_id": self.member.id, "experience_level": "beginner"},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Member is currently paused", response.json()["error"])

    def test_paused_member_blocked_from_regenerating_blank_level_plan(self):
        self.member.is_paused = True
        self.member.workout_plan = make_dummy_workout_plan()
        self.member.workout_experience_level = ""
        self.member.save()

        response = self.client.post(
            self.url,
            {"member_id": self.member.id, "experience_level": "beginner"},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Member is currently paused", response.json()["error"])

    def test_paused_member_blocked_from_replacing_plan_with_different_level(self):
        self.member.is_paused = True
        self.member.workout_plan = make_dummy_workout_plan()
        self.member.workout_experience_level = "beginner"
        self.member.save()

        response = self.client.post(
            self.url,
            {"member_id": self.member.id, "experience_level": "advanced"},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Member is currently paused", response.json()["error"])

    def test_paused_member_can_view_matching_saved_plan(self):
        saved_plan = make_dummy_workout_plan()
        self.member.is_paused = True
        self.member.workout_plan = saved_plan
        self.member.workout_experience_level = "beginner"
        self.member.save()

        response = self.client.post(
            self.url,
            {"member_id": self.member.id, "experience_level": "beginner"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.json()["plan_reused"])

    # -------------------------------------------------------------
    # 8. Intermediate level tests
    # -------------------------------------------------------------
    @patch("groq.Groq")
    def test_intermediate_generation_and_reuse(self, mock_groq):
        intermediate_plan = make_dummy_workout_plan("Dumbbell Romanian Deadlift", sets=3, reps="10-12")
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=json.dumps({"workout_plan": intermediate_plan})))
        ]
        mock_client.chat.completions.create.return_value = mock_response
        mock_groq.return_value = mock_client

        # Generate intermediate
        response = self.client.post(
            self.url,
            {"member_id": self.member.id, "experience_level": "intermediate"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.json()["plan_reused"])
        self.assertEqual(response.json()["experience_level"], "intermediate")

        # Now requesting intermediate again should reuse
        response_reuse = self.client.post(
            self.url,
            {"member_id": self.member.id, "experience_level": "intermediate"},
        )
        self.assertEqual(response_reuse.status_code, status.HTTP_200_OK)
        self.assertTrue(response_reuse.json()["plan_reused"])
        self.assertEqual(response_reuse.json()["experience_level"], "intermediate")

    # -------------------------------------------------------------
    # 9. Access control and validation tests
    # -------------------------------------------------------------
    def test_unauthenticated_request_rejected(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            self.url,
            {"member_id": self.member.id, "experience_level": "beginner"},
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_invalid_experience_level_rejected(self):
        response = self.client.post(
            self.url,
            {"member_id": self.member.id, "experience_level": "expert"},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Choose beginner, intermediate or advanced", response.json()["error"])

    def test_missing_member_id_rejected(self):
        response = self.client.post(
            self.url,
            {"experience_level": "beginner"},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Member ID is required", response.json()["error"])

    def test_tenant_isolation(self):
        other_tenant = Tenant.objects.create(name="Beta Gym", slug="beta-gym")
        other_member = Member.objects.create(
            id="OTHER_001",
            name="Other Member",
            phone="1112223334",
            tenant=other_tenant,
        )
        response = self.client.post(
            self.url,
            {"member_id": other_member.id, "experience_level": "beginner"},
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
