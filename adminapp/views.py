from django.http import JsonResponse
import json
from datetime import datetime, date, timedelta

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated, BasePermission
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.shortcuts import get_object_or_404
from django.db.models import Sum
from django.contrib.auth import get_user_model

User = get_user_model()

from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from functools import wraps


def role_required(allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):

            if not request.user.is_authenticated:
                return JsonResponse(
                    {"error": "Authentication required"},
                    status=401
                )

            if request.user.role not in allowed_roles:
                return JsonResponse(
                    {"error": "Permission denied"},
                    status=403
                )

            if (
                request.user.role != "SUPER_ADMIN"
                and request.user.tenant_id is None
            ):
                return JsonResponse(
                    {"error": "User is not assigned to a tenant"},
                    status=403
                )

            return view_func(request, *args, **kwargs)

        return wrapper
    return decorator


def get_user_scope(user):
    """
    Returns the tenant and branch scope for the logged-in user.
    """

    if user.role == "SUPER_ADMIN":
        return {
            "tenant": None,
            "branch": None,
            "all_access": True,
        }

    if user.role == "TENANT_ADMIN":
        return {
            "tenant": user.tenant,
            "branch": None,
            "all_access": False,
        }

    if user.role in ["BRANCH_ADMIN", "STAFF"]:
        return {
            "tenant": user.tenant,
            "branch": user.branch,
            "all_access": False,
        }

    return {
        "tenant": None,
        "branch": None,
        "all_access": False,
    }


import csv
import io
import uuid

from .models import (
    Branch, Enquiry, Expense, GymEquipment, Payment, Product,
    Sales_product, Member, Income, MemberPause, Staffs, Plan,
)
from .serializers import GymEquipmentSerializer
from .tenant_utils import get_tenant, get_branch_filter


# ============================================================
# IMPORT CSV  (tenant-stamped on every created row)
# ============================================================

IMPORT_CONFIG = {
    "member": {
        "model": Member,
        "mapping": {
            "first_name": "name",
            "phone": "phone",
            "email": "email",
            "plan": "plan",
            "age": "age",
        },
    },
    "staff": {
        "model": Staffs,
        "mapping": {
            "first_name": "name",
            "number": "phone",
            "salary": "salary",
            "joindate": "joining_date",
        },
    },
}


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def import_csv(request):
    tenant = get_tenant(request)

    csv_file = request.FILES.get("file")
    model_type = request.data.get("model")

    if not csv_file:
        return Response({"success": False, "error": "CSV file is required."}, status=status.HTTP_400_BAD_REQUEST)

    if not model_type:
        return Response({"success": False, "error": "model is required."}, status=status.HTTP_400_BAD_REQUEST)

    config = IMPORT_CONFIG.get(model_type)
    if not config:
        return Response({"success": False, "error": f"Unsupported model: {model_type}"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        decoded_file = csv_file.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(decoded_file))

        Model = config["model"]
        mapping = config["mapping"]

        imported = []
        skipped = []

        for row_number, row in enumerate(reader, start=2):
            try:
                data = {"tenant": tenant}  # <-- stamp tenant on every imported row

                for csv_field, model_field in mapping.items():
                    value = row.get(csv_field, "")
                    if value is not None:
                        value = value.strip()
                    if value != "":
                        data[model_field] = value

                if model_type == "member":
                    data["id"] = str(uuid.uuid4())
                    if "age" in data:
                        data["age"] = int(data["age"])

                if model_type == "staff":
                    if "salary" in data:
                        data["salary"] = float(data["salary"])

                obj = Model.objects.create(**data)
                imported.append({"row": row_number, "id": obj.id})

            except Exception as e:
                skipped.append({"row": row_number, "error": str(e)})

        return Response({
            "success": True,
            "model": model_type,
            "imported_count": len(imported),
            "skipped_count": len(skipped),
            "imported": imported,
            "skipped": skipped,
        })

    except Exception as e:
        return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_superuser


# ============================================================
# LOGIN — now embeds tenant/role/branch in the token + response
# ============================================================

@api_view(["POST"])
@permission_classes([AllowAny])
def admin_login(request):
    username = request.data.get("username")
    password = request.data.get("password")

    if not username or not password:
        return JsonResponse({"error": "Username and password are required"}, status=404)

    user = authenticate(username=username, password=password)

    if user is None:
        return JsonResponse({"error": "Invalid username or password"}, status=401)

    if not user.is_superuser and not getattr(user, "tenant_id", None):
        # Every non-superuser account must belong to a tenant to log in
        return JsonResponse({"error": "This account is not linked to any gym."}, status=403)

    refresh = RefreshToken.for_user(user)

    # Embed tenant context in the JWT itself so DRF auth alone carries it
    refresh["tenant_id"] = user.tenant_id
    refresh["role"] = getattr(user, "role", None)
    refresh["branch_id"] = getattr(user, "branch_id", None)

    return JsonResponse(
        {
            "message": "Login successful",
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "is_staff": user.is_staff,
                "is_superuser": user.is_superuser,
                "role": getattr(user, "role", None),
                "tenant_id": user.tenant_id,
                "tenant_name": user.tenant.name if getattr(user, "tenant", None) else None,
                "branch_id": getattr(user, "branch_id", None),
                "branch_name": user.branch.name if getattr(user, "branch", None) else None,
            },
        },
        status=200,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def change_password(request):
    user = request.user
    current_password = request.data.get("current_password")
    new_password = request.data.get("new_password")
    confirm_password = request.data.get("confirm_password")

    if not current_password or not new_password or not confirm_password:
        return JsonResponse({"error": "All fields are required"}, status=400)

    if not user.check_password(current_password):
        return JsonResponse({"error": "Current password is incorrect"}, status=400)

    if new_password != confirm_password:
        return JsonResponse({"error": "New password and confirm password do not match"}, status=400)

    if len(new_password) < 6:
        return JsonResponse({"error": "New password must be at least 6 characters long"}, status=400)

    user.set_password(new_password)
    user.save()

    return JsonResponse({"message": "Password changed successfully"}, status=200)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_profile_view(request):
    user = request.user

    return JsonResponse({
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": f"{user.first_name} {user.last_name}".strip() or user.username,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "role": getattr(user, "role", None),
        "tenant_id": getattr(user, "tenant_id", None),
        "branch_id": getattr(user, "branch_id", None),
    })


from django.http import JsonResponse
from datetime import datetime, date, timedelta

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from .models import Member, Plan, Branch, MemberPause
from .tenant_utils import get_tenant, get_branch_filter


# ============================================================
# MEMBERS
# ============================================================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_member(request):
    tenant = get_tenant(request)

    # SUPER_ADMIN must select a tenant
    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse(
            {"error": "Please select a tenant before creating a member"},
            status=400
        )

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    try:
        # Generate member ID only within the selected tenant
        last_member = (
            Member.objects
            .filter(tenant=tenant)
            .order_by("-id")
            .first()
        )

        next_id = (
            f"{int(last_member.id) + 1:04d}"
            if last_member
            else "0001"
        )

        # -------------------------------------------------
        # Inputs
        # -------------------------------------------------

        plan_id = request.POST.get("plan")
        branch_id = request.POST.get("branch")
        join_date_str = request.POST.get("join_date")

        phone = request.POST.get("phone", "").strip()
        email = request.POST.get("email", "").strip().lower()

        goal = request.POST.get("goal")
        food_category = request.POST.get("food_category")

        # -------------------------------------------------
        # Required fields
        # -------------------------------------------------

        if not plan_id:
            return JsonResponse(
                {"error": "Plan is required"},
                status=400
            )

        if not branch_id:
            return JsonResponse(
                {"error": "Branch is required"},
                status=400
            )

        if not join_date_str:
            return JsonResponse(
                {"error": "Join date is required"},
                status=400
            )

        # -------------------------------------------------
        # Phone validation
        # -------------------------------------------------

        if not (phone.isdigit() and len(phone) == 10):
            return JsonResponse(
                {"error": "Enter a valid 10-digit mobile number"},
                status=400
            )

        if Member.objects.filter(
            tenant=tenant,
            phone=phone
        ).exists():
            return JsonResponse(
                {"error": "Mobile number already exists"},
                status=400
            )

        # -------------------------------------------------
        # Email validation
        # -------------------------------------------------

        if email and Member.objects.filter(
            tenant=tenant,
            email=email
        ).exists():
            return JsonResponse(
                {"error": "Email already exists"},
                status=400
            )

        # -------------------------------------------------
        # Plan validation
        # -------------------------------------------------

        try:
            plan = Plan.objects.get(
                id=plan_id,
                tenant=tenant
            )
        except Plan.DoesNotExist:
            return JsonResponse(
                {"error": "Invalid plan selected"},
                status=400
            )

        # -------------------------------------------------
        # Branch validation
        # -------------------------------------------------

        # Branch Admin and Staff MUST use their own branch.
        if request.user.role in ["BRANCH_ADMIN", "STAFF"]:

            if not request.user.branch_id:
                return JsonResponse(
                    {"error": "User is not assigned to a branch"},
                    status=403
                )

            branch = Branch.objects.filter(
                id=request.user.branch_id,
                tenant=tenant
            ).first()

            if not branch:
                return JsonResponse(
                    {"error": "Invalid branch assignment"},
                    status=403
                )

            # Ignore any branch_id sent by frontend.
            branch_id = request.user.branch_id

        else:
            # TENANT_ADMIN / SUPER_ADMIN
            try:
                branch = Branch.objects.get(
                    id=branch_id,
                    tenant=tenant
                )
            except Branch.DoesNotExist:
                return JsonResponse(
                    {"error": "Invalid Branch selected"},
                    status=400
                )

        # -------------------------------------------------
        # Join date
        # -------------------------------------------------

        try:
            join_date = datetime.strptime(
                join_date_str,
                "%Y-%m-%d"
            ).date()

        except ValueError:
            return JsonResponse(
                {"error": "Invalid join date"},
                status=400
            )

        # -------------------------------------------------
        # Expiry date
        # -------------------------------------------------

        duration = int(plan.duration or 0)

        expiry_date = (
            join_date +
            timedelta(days=duration)
        )

        # -------------------------------------------------
        # Height / Weight / BMI
        # -------------------------------------------------

        try:
            weight = float(
                request.POST.get("weight") or 0
            )

            height = float(
                request.POST.get("height") or 0
            )

        except ValueError:
            return JsonResponse(
                {"error": "Invalid height or weight"},
                status=400
            )

        bmi = None

        if height > 0 and weight > 0:

            height_m = height / 100

            bmi = round(
                weight / (height_m * height_m),
                2
            )

        # -------------------------------------------------
        # Paid amount
        # -------------------------------------------------

        try:
            paid_amount = float(
                request.POST.get("paid_amount") or 0
            )

        except ValueError:
            return JsonResponse(
                {"error": "Invalid paid amount"},
                status=400
            )

        if paid_amount < 0:
            return JsonResponse(
                {"error": "Paid amount cannot be negative"},
                status=400
            )

        # -------------------------------------------------
        # Plan amount
        # -------------------------------------------------

        plan_amount = float(
            plan.price or 0
        )

        if paid_amount > plan_amount:
            return JsonResponse(
                {
                    "error":
                    "Paid amount cannot exceed plan price"
                },
                status=400
            )

        due_amount = max(
            plan_amount - paid_amount,
            0
        )

        # -------------------------------------------------
        # Photo
        # -------------------------------------------------

        photo = request.FILES.get("photo")

        # -------------------------------------------------
        # Create member
        # -------------------------------------------------

        member = Member.objects.create(

            # Tenant is ALWAYS taken from authenticated user
            # / selected tenant.
            tenant=tenant,

            id=next_id,

            name=request.POST.get("name"),

            phone=phone,

            email=email,

            plan=plan,

            branch=branch,

            join_date=join_date,

            photo=photo,

            height=height,

            weight=weight,

            bmi=bmi,

            goal=goal,

            food_category=food_category,

            age=request.POST.get("age"),

            blood_group=request.POST.get(
                "blood_group"
            ),

            location=request.POST.get(
                "location"
            ),

            adhaar_number=request.POST.get(
                "adhaar_number"
            ),

            gender=request.POST.get(
                "gender"
            ),

            paid_amount=paid_amount,

            due_amount=due_amount,

            expiry_date=expiry_date,

            status="Active",
        )

        return JsonResponse(
            {
                "message": "Member created successfully",
                "member_id": member.id,
            },
            status=201
        )

    except Exception as e:

        return JsonResponse(
            {
                "error": str(e)
            },
            status=500
        )

def auto_resume_member(member, today):
    if member.is_paused and member.pause_expiry_date:
        if today >= member.pause_expiry_date:
            active_pause = MemberPause.objects.filter(member=member, end_date__isnull=True).first()
            if active_pause:
                paused_days = (today - active_pause.start_date).days
                active_pause.end_date = today
                active_pause.paused_days = paused_days
                active_pause.save()
                if member.expiry_date:
                    member.expiry_date += timedelta(days=paused_days)

            member.is_paused = False
            member.pause_start_date = None
            member.pause_expiry_date = None
            member.status = "Active"
            member.save()

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_members(request):

    tenant = get_tenant(request)
    today = date.today()

    # SUPER_ADMIN must select a tenant
    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse(
            {"error": "Please select a tenant before viewing members"},
            status=400
        )

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    members = (
        Member.objects
        .filter(
            tenant=tenant,
            **get_branch_filter(request, tenant)
        )
        .select_related("plan", "branch")
        .order_by("-id")
    )

    data = []

    for member in members:

        # -------------------------------------------------
        # Auto resume logic
        # -------------------------------------------------

        auto_resume_member(member, today)

        # -------------------------------------------------
        # Member status logic
        # -------------------------------------------------

        if member.is_paused:

            member.status = "Paused"

        elif member.expiry_date:

            if member.expiry_date < today:

                days_expired = (
                    today - member.expiry_date
                ).days

                if days_expired <= 7:
                    member.status = "Expired"
                else:
                    member.status = "Blocked"

            else:
                member.status = "Active"

        else:
            member.status = "Active"

        member.save()

        # -------------------------------------------------
        # Pause calculations
        # -------------------------------------------------

        month_start = today.replace(day=1)

        next_month = (
            today.replace(
                year=today.year + 1,
                month=1,
                day=1
            )
            if today.month == 12
            else today.replace(
                month=today.month + 1,
                day=1
            )
        )

        month_end = next_month - timedelta(days=1)

        pauses = MemberPause.objects.filter(
            member=member,
            start_date__gte=month_start,
            start_date__lte=month_end
        )

        used_days = sum(
            p.paused_days
            for p in pauses
            if p.end_date
        )

        remaining_days = max(
            15 - used_days,
            0
        )

        pause_count = pauses.count()

        # -------------------------------------------------
        # Response
        # -------------------------------------------------

        data.append({

            "id": member.id,

            "name": member.name,

            "phone": member.phone,

            "email": member.email,

            "age": member.age,

            "gender": member.gender,

            "blood_group": member.blood_group,

            "location": member.location,

            "height": member.height,

            "weight": member.weight,

            "bmi": member.bmi,

            "goal": member.get_goal_display(),

            "food_category": (
                member.get_food_category_display()
            ),

            # IMPORTANT:
            # Do not return member.plan directly.
            "plan": (
                {
                    "id": member.plan.id,
                    "name": member.plan.name,
                    "duration": member.plan.duration,
                    "price": member.plan.price,
                }
                if member.plan
                else None
            ),

            # IMPORTANT:
            # Do not return member.branch directly.
            "branch": (
                {
                    "id": member.branch.id,
                    "name": member.branch.name,
                    "location": member.branch.location,
                }
                if member.branch
                else None
            ),

            "join_date": member.join_date,

            "expiry_date": (
                member.expiry_date.isoformat()
                if member.expiry_date
                else None
            ),

            "paid_amount": member.paid_amount,

            "due_amount": member.due_amount,

            "status": member.status,

            "photo": (
                member.photo.url
                if member.photo
                else None
            ),

            "pause_start_date": (
                member.pause_start_date.isoformat()
                if member.pause_start_date
                else None
            ),

            "pause_expiry_date": (
                member.pause_expiry_date.isoformat()
                if member.pause_expiry_date
                else None
            ),

            "is_paused": member.is_paused,

            "pause_days_used": used_days,

            "pause_days_remaining": remaining_days,

            "pause_count": pause_count,
        })

    return JsonResponse(
        data,
        safe=False
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_member(request, member_id):

    tenant = get_tenant(request)

    # SUPER_ADMIN without tenant selection
    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse(
            {
                "error": "Please select a tenant"
            },
            status=400
        )

    if tenant is None:
        return JsonResponse(
            {
                "error": "User is not assigned to a tenant"
            },
            status=403
        )

    try:

        member = Member.objects.select_related(
            "plan",
            "branch"
        ).get(
            id=member_id,
            tenant=tenant,
            **get_branch_filter(
                request,
                tenant
            )
        )

        # -------------------------------------------------
        # Existing status logic
        # -------------------------------------------------

        if member.is_paused:

            member_status = "Paused"

        elif member.expiry_date:

            today = date.today()

            if member.expiry_date < today:

                days_expired = (
                    today -
                    member.expiry_date
                ).days

                if days_expired <= 7:

                    member_status = "Expired"

                else:

                    member_status = "Blocked"

            else:

                member_status = "Active"

        else:

            member_status = "Active"

        if member.status != member_status:

            member.status = member_status

            member.save(
                update_fields=["status"]
            )

        # -------------------------------------------------
        # Response
        # -------------------------------------------------

        return JsonResponse(
            {
                "id": member.id,

                "name": member.name,

                "phone": member.phone,

                "email": member.email,

                "plan": (
                    {
                        "id": member.plan.id,
                        "name": member.plan.name,
                        "duration": member.plan.duration,
                        "price": member.plan.price,
                    }
                    if member.plan
                    else None
                ),

                "branch": (
                    {
                        "id": member.branch.id,
                        "name": member.branch.name,
                        "location": member.branch.location,
                    }
                    if member.branch
                    else None
                ),

                "join_date": member.join_date,

                "status": member_status,

                "photo": (
                    member.photo.url
                    if member.photo
                    else None
                ),

                "height": member.height,

                "weight": member.weight,

                "bmi": member.bmi,

                "age": member.age,

                "goal": member.goal,

                "food_category": member.food_category,

                "blood_group": member.blood_group,

                "location": member.location,

                "adhaar_number": member.adhaar_number,

                "gender": member.gender,

                "paid_amount": member.paid_amount,

                "due_amount": member.due_amount,

                "expiry_date": (
                    member.expiry_date.isoformat()
                    if member.expiry_date
                    else None
                ),

                "is_paused": member.is_paused,

                "pause_start_date": (
                    member.pause_start_date.isoformat()
                    if member.pause_start_date
                    else None
                ),

                "used_pause_days": member.used_pause_days,

                "pause_expiry_date": (
                    member.pause_expiry_date.isoformat()
                    if member.pause_expiry_date
                    else None
                ),
            },
            status=200
        )

    except Member.DoesNotExist:

        return JsonResponse(
            {
                "error": "Member not found"
            },
            status=404
        )

    except Exception as e:

        return JsonResponse(
            {
                "error": str(e)
            },
            status=500
        )

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def update_member(request, member_id):

    tenant = get_tenant(request)

    # SUPER_ADMIN without tenant selection
    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse(
            {
                "error": "Please select a tenant"
            },
            status=400
        )

    if tenant is None:
        return JsonResponse(
            {
                "error": "User is not assigned to a tenant"
            },
            status=403
        )

    try:

        # -------------------------------------------------
        # IMPORTANT:
        # Get member only inside current tenant + branch
        # -------------------------------------------------

        member = Member.objects.get(
            id=member_id,
            tenant=tenant,
            **get_branch_filter(
                request,
                tenant
            )
        )

        # -------------------------------------------------
        # Inputs
        # -------------------------------------------------

        name = request.data.get(
            "name",
            member.name
        )

        phone = request.data.get(
            "phone",
            member.phone
        )

        email = request.data.get(
            "email",
            member.email
        )

        plan_id = request.data.get(
            "plan"
        )

        join_date_str = request.data.get(
            "join_date"
        )

        goal = request.data.get(
            "goal",
            member.goal
        )

        food_category = request.data.get(
            "food_category",
            member.food_category
        )

        # -------------------------------------------------
        # Phone
        # -------------------------------------------------

        phone = str(phone).strip()

        if not (
            phone.isdigit()
            and len(phone) == 10
        ):
            return JsonResponse(
                {
                    "error":
                    "Enter a valid 10-digit mobile number"
                },
                status=400
            )

        # Check duplicate phone
        if Member.objects.filter(
            tenant=tenant,
            phone=phone
        ).exclude(
            id=member.id
        ).exists():

            return JsonResponse(
                {
                    "error":
                    "Mobile number already exists"
                },
                status=400
            )

        # -------------------------------------------------
        # Email
        # -------------------------------------------------

        if email:

            email = str(email).strip().lower()

            if Member.objects.filter(
                tenant=tenant,
                email=email
            ).exclude(
                id=member.id
            ).exists():

                return JsonResponse(
                    {
                        "error":
                        "Email already exists"
                    },
                    status=400
                )

        # -------------------------------------------------
        # Plan
        # -------------------------------------------------

        selected_plan = member.plan

        if plan_id:

            try:

                selected_plan = Plan.objects.get(
                    id=plan_id,
                    tenant=tenant
                )

            except Plan.DoesNotExist:

                return JsonResponse(
                    {
                        "error":
                        "Invalid plan selected"
                    },
                    status=400
                )

        # -------------------------------------------------
        # Join date
        # -------------------------------------------------

        if join_date_str:

            try:

                join_date = datetime.strptime(
                    str(join_date_str),
                    "%Y-%m-%d"
                ).date()

            except ValueError:

                return JsonResponse(
                    {
                        "error":
                        "Invalid join date"
                    },
                    status=400
                )

        else:

            join_date = member.join_date
            if isinstance(join_date, str):
                try:

                    join_date = datetime.strptime(
                        join_date,
                        "%Y-%m-%d"
                    ).date()
                except ValueError:

                    join_date = None
        try:
            weight = float(
                request.data.get(
                    "weight",
                    member.weight or 0
                ) or 0
            )
            height = float(
                request.data.get(
                    "height",
                    member.height or 0
                ) or 0
            )

        except ValueError:
            return JsonResponse(
                {
                    "error":
                    "Invalid height or weight"
                },
                status=400
            )

        bmi = member.bmi

        if height > 0 and weight > 0:

            height_m = height / 100

            bmi = round(
                weight /
                (height_m * height_m),
                2
            )
        try:

            paid_amount = float(
                request.data.get(
                    "paid_amount",
                    member.paid_amount or 0
                ) or 0
            )
        except ValueError:

            return JsonResponse(
                {
                    "error":
                    "Invalid paid amount"
                },
                status=400
            )

        if paid_amount < 0:
            return JsonResponse(
                {
                    "error":
                    "Paid amount cannot be negative"
                },
                status=400
            )
        plan_amount = float(
            selected_plan.price or 0
        )

        if paid_amount > plan_amount:
            return JsonResponse(
                {
                    "error":
                    "Paid amount cannot exceed plan price"
                },
                status=400
            )

        due_amount = max(
            plan_amount - paid_amount,
            0
        )
        expiry_date = member.expiry_date
        if join_date and selected_plan:
            duration = int(
                selected_plan.duration or 0
            )

            expiry_date = (
                join_date +
                timedelta(days=duration)
            )
        member.name = name
        member.phone = phone
        member.email = email
        member.plan = selected_plan
        member.height = height
        member.weight = weight
        member.bmi = bmi
        member.goal = goal
        member.food_category = food_category
        member.age = request.data.get("age",member.age)

        member.blood_group = request.data.get(
            "blood_group",
            member.blood_group
        )

        member.location = request.data.get(
            "location",
            member.location
        )

        member.adhaar_number = request.data.get(
            "adhaar_number",
            member.adhaar_number
        )

        member.gender = request.data.get(
            "gender",
            member.gender
        )
        member.paid_amount = paid_amount
        member.due_amount = due_amount
        if join_date:
            member.join_date = join_date
        member.expiry_date = expiry_date
        photo = request.FILES.get("photo")
        if photo:
            member.photo = photo
        member.save()
        return JsonResponse(
            {
                "message":
                "Member updated successfully",

                "member_id":
                member.id,
            },
            status=200
        )
    except Member.DoesNotExist:

        return JsonResponse(
            {
                "error":
                "Member not found"
            },
            status=404
        )
    except Exception as e:
        return JsonResponse(
            {
                "error":
                str(e)
            },
            status=500
        )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_member(request, member_id):
    tenant = get_tenant(request)
    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse(
            {"error": "Please select a tenant before deleting a member"},
            status=400
        )
    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    if request.user.role == "STAFF":
        return JsonResponse(
            {"error": "Staff members are not allowed to delete members"},
            status=403
        )

    if request.user.role not in [
        "SUPER_ADMIN",
        "TENANT_ADMIN",
        "BRANCH_ADMIN"
    ]:
        return JsonResponse(
            {"error": "Permission denied"},
            status=403
        )
    try:
        member = Member.objects.get(
            id=member_id,
            tenant=tenant,
            **get_branch_filter(request, tenant)
        )

    except Member.DoesNotExist:

        return JsonResponse(
            {"error": "Member not found or access denied"},
            status=404
        )
    member.delete()
    return JsonResponse(
        {
            "message": "Member deleted successfully",
            "member_id": member_id
        },
        status=200
    )

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_plan(request):
    tenant = get_tenant(request)

    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse(
            {"error": "Please select a tenant before creating a plan"},
            status=400
        )

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    if request.user.role not in ["SUPER_ADMIN", "TENANT_ADMIN"]:
        return JsonResponse(
            {"error": "Only tenant admins can create plans"},
            status=403
        )

    Plan.objects.create(
        tenant=tenant,
        name=request.POST.get("name"),
        duration=request.POST.get("duration"),
        price=request.POST.get("price"),
    )

    return JsonResponse({"message": "success"}, status=201)



@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_plans(request):
    tenant = get_tenant(request)

    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse(
            {"error": "Please select a tenant before viewing plans"},
            status=400
        )

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    plans = list(
        Plan.objects
        .filter(tenant=tenant)
        .order_by("id")
        .values()
    )

    return JsonResponse(plans, safe=False)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def update_plan(request, plan_id):
    tenant = get_tenant(request)

    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse(
            {"error": "Please select a tenant before updating a plan"},
            status=400
        )

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    # All roles can update plans except none
    # STAFF is also allowed
    if request.user.role not in [
        "SUPER_ADMIN",
        "TENANT_ADMIN",
        "BRANCH_ADMIN",
        "STAFF"
    ]:
        return JsonResponse(
            {"error": "Not permitted"},
            status=403
        )

    try:
        plan = Plan.objects.get(
            id=plan_id,
            tenant=tenant
        )
    except Plan.DoesNotExist:
        return JsonResponse(
            {"error": "Plan not found"},
            status=404
        )

    plan.name = request.POST.get("name")
    plan.duration = request.POST.get("duration")
    plan.price = request.POST.get("price")
    plan.save()

    return JsonResponse({
        "message": "Plan updated successfully"
    })

@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_plan(request, plan_id):
    tenant = get_tenant(request)

    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse(
            {"error": "Please select a tenant before deleting a plan"},
            status=400
        )

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    # STAFF cannot delete
    if request.user.role not in [
        "SUPER_ADMIN",
        "TENANT_ADMIN",
        "BRANCH_ADMIN"
    ]:
        return JsonResponse(
            {"error": "Staff are not permitted to delete plans"},
            status=403
        )

    try:
        plan = Plan.objects.get(
            id=plan_id,
            tenant=tenant
        )
    except Plan.DoesNotExist:
        return JsonResponse(
            {"error": "Plan not found"},
            status=404
        )

    plan.delete()

    return JsonResponse({
        "message": "Plan deleted successfully"
    })

    
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_branch(request):
    tenant = get_tenant(request)

    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse(
            {"error": "Please select a tenant before creating a branch"},
            status=400
        )

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    if request.user.role not in ["SUPER_ADMIN", "TENANT_ADMIN"]:
        return JsonResponse(
            {"error": "Only tenant admins can create branches"},
            status=403
        )

    phone = request.POST.get("phone")
    capacity = request.POST.get("capacity")

    if not phone or not phone.isdigit() or len(phone) != 10:
        return JsonResponse(
            {"error": "Enter a valid 10-digit mobile number"},
            status=400
        )

    Branch.objects.create(
        tenant=tenant,
        name=request.POST.get("name"),
        location=request.POST.get("location"),
        manager_name=request.POST.get("manager_name"),
        phone=phone,
        capacity=capacity,
    )

    return JsonResponse({"message": "success"}, status=201)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_branches(request):
    tenant = get_tenant(request)
    user = request.user

    if user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse(
            {"error": "Please select a tenant before viewing branches"},
            status=400
        )

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    qs = Branch.objects.filter(tenant=tenant)

    if user.role in ["BRANCH_ADMIN", "STAFF"]:
        if not user.branch_id:
            return JsonResponse(
                {"error": "User is not assigned to a branch"},
                status=403
            )

        qs = qs.filter(id=user.branch_id)

    branches = list(
        qs.order_by("id").values()
    )

    return JsonResponse(branches, safe=False)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_branch_members(request, branch_id):
    tenant = get_tenant(request)

    # SUPER_ADMIN must select a tenant
    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse(
            {"error": "Please select a tenant before viewing branch members"},
            status=400
        )

    # Other users must belong to a tenant
    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    # Get branch only from the selected tenant
    try:
        branch = Branch.objects.get(
            id=branch_id,
            tenant=tenant
        )
    except Branch.DoesNotExist:
        return JsonResponse(
            {"error": "Branch not found or access denied"},
            status=404
        )

    # BRANCH_ADMIN and STAFF can access only their own branch
    if request.user.role in ["BRANCH_ADMIN", "STAFF"]:
        if request.user.branch_id != branch.id:
            return JsonResponse(
                {"error": "You are not permitted to access this branch"},
                status=403
            )

    try:
        members = (
            Member.objects
            .filter(
                tenant=tenant,
                branch=branch
            )
            .select_related("plan", "branch")
        )

        member_data = [
            {
                "id": m.id,
                "name": m.name,
                "phone": m.phone,
                "email": m.email,
                "plan": {
                    "id": m.plan.id,
                    "name": m.plan.name,
                    "duration": m.plan.duration,
                    "price": m.plan.price,
                } if m.plan else None,
            }
            for m in members
        ]

        return JsonResponse({
            "branch": {
                "id": branch.id,
                "name": branch.name,
                "location": branch.location,
            },
            "customers": member_data
        })

    except Exception as e:
        return JsonResponse(
            {"error": str(e)},
            status=500
        )
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def update_branch(request, branch_id):
    tenant = get_tenant(request)

    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse(
            {"error": "Please select a tenant before updating a branch"},
            status=400
        )

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    if request.user.role not in ["SUPER_ADMIN", "TENANT_ADMIN"]:
        return JsonResponse(
            {"error": "Only tenant admins can edit branches"},
            status=403
        )

    try:
        branch = Branch.objects.get(
            id=branch_id,
            tenant=tenant
        )
    except Branch.DoesNotExist:
        return JsonResponse(
            {"error": "Branch not found"},
            status=404
        )

    branch.name = request.POST.get("name")
    branch.location = request.POST.get("location")
    branch.manager_name = request.POST.get("manager_name")
    branch.phone = request.POST.get("phone")
    branch.capacity = request.POST.get("capacity")

    branch.save()

    return JsonResponse({
        "message": "Branch updated successfully"
    })

@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_branch(request, branch_id):
    tenant = get_tenant(request)

    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse(
            {"error": "Please select a tenant before deleting a branch"},
            status=400
        )

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    if request.user.role not in [
        "SUPER_ADMIN",
        "TENANT_ADMIN"
    ]:
        return JsonResponse(
            {"error": "Not permitted"},
            status=403
        )

    try:
        branch = Branch.objects.get(
            id=branch_id,
            tenant=tenant
        )
    except Branch.DoesNotExist:
        return JsonResponse(
            {"error": "Branch not found"},
            status=404
        )

    branch.delete()

    return JsonResponse({
        "message": "Branch deleted successfully"
    })



from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db.models import Sum
from django.http import JsonResponse

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from .models import (
    Member,
    Income,
    Sales_product,
    Expense,
)
from .tenant_utils import get_tenant, get_branch_filter


# =========================================================
# GROWTH CALCULATION
# =========================================================

def calculate_growth(current, previous):
    if previous == 0:
        return 100 if current > 0 else 0

    return round(
        ((current - previous) / previous) * 100,
        2
    )


# =========================================================
# PERIOD DATE CALCULATION
# =========================================================

def get_period_dates(period, selected_date=None):

    if selected_date:

        if isinstance(selected_date, str):
            today = datetime.strptime(
                selected_date,
                "%Y-%m-%d"
            ).date()
        else:
            today = selected_date

    else:
        today = date.today()

    if period == "daily":

        start_date = today
        end_date = today

    elif period == "weekly":

        # Monday -> today
        start_date = today - timedelta(
            days=today.weekday()
        )

        end_date = today

    elif period == "monthly":

        start_date = today.replace(day=1)
        end_date = today

    elif period == "yearly":

        start_date = today.replace(
            month=1,
            day=1
        )

        end_date = today

    else:

        return None, None

    return start_date, end_date


# =========================================================
# DASHBOARD STATS
# =========================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_dashboard_stats(request):

    # =====================================================
    # TENANT
    # =====================================================

    tenant = get_tenant(request)

    # SUPER_ADMIN must select a tenant
    if request.user.role == "SUPER_ADMIN" and tenant is None:

        return JsonResponse(
            {
                "error":
                    "Please select a tenant before viewing dashboard"
            },
            status=400
        )

    # All other users must belong to a tenant
    if tenant is None:

        return JsonResponse(
            {
                "error":
                    "User is not assigned to a tenant"
            },
            status=403
        )


    # =====================================================
    # BRANCH FILTER
    # =====================================================

    branch_filter = get_branch_filter(
        request,
        tenant
    )


    # =====================================================
    # PERIOD
    # =====================================================

    period = request.GET.get(
        "period",
        "daily"
    ).lower()

    date_str = request.GET.get("date")


    # =====================================================
    # SELECTED DATE
    # =====================================================

    if date_str:

        try:

            today = datetime.strptime(
                date_str,
                "%Y-%m-%d"
            ).date()

        except ValueError:

            return JsonResponse(
                {
                    "error":
                        "Invalid date format. Use YYYY-MM-DD"
                },
                status=400
            )

    else:

        today = date.today()


    # =====================================================
    # PERIOD DATES
    # =====================================================

    start_date, end_date = get_period_dates(
        period,
        today
    )

    if start_date is None:

        return JsonResponse(
            {
                "error":
                    "Invalid period. Use daily, weekly, monthly or yearly."
            },
            status=400
        )


    # =====================================================
    # PREVIOUS MONTH
    # =====================================================

    if today.month == 1:

        last_month = 12
        last_year = today.year - 1

    else:

        last_month = today.month - 1
        last_year = today.year


    # =====================================================
    # MEMBERS
    # Tenant + Branch scoped
    # =====================================================

    member_qs = Member.objects.filter(
        tenant=tenant,
        **branch_filter
    ).select_related(
        "plan",
        "branch"
    )


    # =====================================================
    # MEMBER COUNTS
    # =====================================================

    total_members = member_qs.count()

    active_members = member_qs.filter(
        status="Active"
    ).count()

    blocked_members = member_qs.filter(
        status="Blocked"
    ).count()

    expired_members = member_qs.filter(
        status="Expired"
    ).count()

    paused_members = member_qs.filter(
        is_paused=True
    ).count()

    pending_payments = member_qs.filter(
        due_amount__gt=0
    ).count()


    # =====================================================
    # UPCOMING EXPIRIES
    # =====================================================

    next_week = today + timedelta(days=7)

    expiries = (
        member_qs
        .filter(
            status="Active",
            expiry_date__gte=today,
            expiry_date__lte=next_week
        )
        .order_by("expiry_date")
    )


    upcoming_expiries_list = [

        {
            "id": member.id,
            "name": member.name,
            "phone": member.phone,
            "expiry_date": (
                member.expiry_date.isoformat()
                if member.expiry_date
                else None
            ),
            "due_amount": member.due_amount,
            "plan": (
                member.plan.name
                if member.plan
                else None
            ),
        }

        for member in expiries
    ]


    # =====================================================
    # RECENT REGISTRATIONS
    # =====================================================

    recent = (
        member_qs
        .select_related("plan", "branch")
        .order_by("-id")[:5]
    )


    recent_registrations = [

        {
            "id": member.id,

            "name": member.name,

            "phone": member.phone,

            "email": member.email,

            "plan": (
                {
                    "id": member.plan.id,
                    "name": member.plan.name,
                    "duration": member.plan.duration,
                    "price": member.plan.price,
                }
                if member.plan
                else None
            ),

            "branch": (
                {
                    "id": member.branch.id,
                    "name": member.branch.name,
                    "location": member.branch.location,
                }
                if member.branch
                else None
            ),

            "join_date": member.join_date,

        }

        for member in recent
    ]


    # =====================================================
    # FINANCIAL DATA
    #
    # Current models only have tenant.
    # They do NOT have branch.
    #
    # Therefore financial data is tenant scoped.
    # =====================================================

    income_qs = Income.objects.filter(
        tenant=tenant
    )

    sales_qs = Sales_product.objects.filter(
        tenant=tenant
    )

    expense_qs = Expense.objects.filter(
        tenant=tenant
    )


    # =====================================================
    # TOTAL / ALL-TIME INCOME
    # =====================================================

    total_membership_income = (
        income_qs
        .aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0")
    )


    total_product_income = (
        sales_qs
        .aggregate(
            total=Sum("total_amount")
        )["total"]
        or Decimal("0")
    )


    total_income = (
        total_membership_income
        + total_product_income
    )


    # =====================================================
    # PERIOD INCOME
    # =====================================================

    period_membership_income = (
        income_qs
        .filter(
            date__date__gte=start_date,
            date__date__lte=end_date
        )
        .aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0")
    )


    period_product_income = (
        sales_qs
        .filter(
            sold_at__date__gte=start_date,
            sold_at__date__lte=end_date
        )
        .aggregate(
            total=Sum("total_amount")
        )["total"]
        or Decimal("0")
    )


    period_income = (
        period_membership_income
        + period_product_income
    )


    # =====================================================
    # TODAY INCOME
    # =====================================================

    today_membership_income = (
        income_qs
        .filter(
            date__date=today
        )
        .aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0")
    )


    today_product_income = (
        sales_qs
        .filter(
            sold_at__date=today
        )
        .aggregate(
            total=Sum("total_amount")
        )["total"]
        or Decimal("0")
    )


    today_income = (
        today_membership_income
        + today_product_income
    )


    # =====================================================
    # MONTHLY INCOME
    # =====================================================

    monthly_membership_income = (
        income_qs
        .filter(
            date__year=today.year,
            date__month=today.month
        )
        .aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0")
    )


    monthly_product_income = (
        sales_qs
        .filter(
            sold_at__year=today.year,
            sold_at__month=today.month
        )
        .aggregate(
            total=Sum("total_amount")
        )["total"]
        or Decimal("0")
    )


    monthly_income = (
        monthly_membership_income
        + monthly_product_income
    )


    # =====================================================
    # YEARLY INCOME
    # =====================================================

    yearly_membership_income = (
        income_qs
        .filter(
            date__year=today.year
        )
        .aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0")
    )


    yearly_product_income = (
        sales_qs
        .filter(
            sold_at__year=today.year
        )
        .aggregate(
            total=Sum("total_amount")
        )["total"]
        or Decimal("0")
    )


    yearly_income = (
        yearly_membership_income
        + yearly_product_income
    )


    # =====================================================
    # LAST MONTH INCOME
    # =====================================================

    last_month_membership_income = (
        income_qs
        .filter(
            date__year=last_year,
            date__month=last_month
        )
        .aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0")
    )


    last_month_product_income = (
        sales_qs
        .filter(
            sold_at__year=last_year,
            sold_at__month=last_month
        )
        .aggregate(
            total=Sum("total_amount")
        )["total"]
        or Decimal("0")
    )


    last_month_income = (
        last_month_membership_income
        + last_month_product_income
    )


    # =====================================================
    # SALES
    # =====================================================

    total_sales = (
        sales_qs
        .aggregate(
            total=Sum("total_amount")
        )["total"]
        or Decimal("0")
    )


    period_sales = (
        sales_qs
        .filter(
            sold_at__date__gte=start_date,
            sold_at__date__lte=end_date
        )
        .aggregate(
            total=Sum("total_amount")
        )["total"]
        or Decimal("0")
    )


    today_sales = (
        sales_qs
        .filter(
            sold_at__date=today
        )
        .aggregate(
            total=Sum("total_amount")
        )["total"]
        or Decimal("0")
    )


    monthly_sales = (
        sales_qs
        .filter(
            sold_at__year=today.year,
            sold_at__month=today.month
        )
        .aggregate(
            total=Sum("total_amount")
        )["total"]
        or Decimal("0")
    )


    last_month_sales = (
        sales_qs
        .filter(
            sold_at__year=last_year,
            sold_at__month=last_month
        )
        .aggregate(
            total=Sum("total_amount")
        )["total"]
        or Decimal("0")
    )


    yearly_sales = (
        sales_qs
        .filter(
            sold_at__year=today.year
        )
        .aggregate(
            total=Sum("total_amount")
        )["total"]
        or Decimal("0")
    )


    # =====================================================
    # EXPENSE
    # =====================================================

    total_expense = (
        expense_qs
        .aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0")
    )


    period_expense = (
        expense_qs
        .filter(
            date__gte=start_date,
            date__lte=end_date
        )
        .aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0")
    )


    today_expense = (
        expense_qs
        .filter(
            date=today
        )
        .aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0")
    )


    monthly_expense = (
        expense_qs
        .filter(
            date__year=today.year,
            date__month=today.month
        )
        .aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0")
    )


    last_month_expense = (
        expense_qs
        .filter(
            date__year=last_year,
            date__month=last_month
        )
        .aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0")
    )


    yearly_expense = (
        expense_qs
        .filter(
            date__year=today.year
        )
        .aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0")
    )


    # =====================================================
    # PROFIT / LOSS
    # =====================================================

    period_profit = max(
        period_income - period_expense,
        Decimal("0")
    )

    period_loss = max(
        period_expense - period_income,
        Decimal("0")
    )


    today_profit = max(
        today_income - today_expense,
        Decimal("0")
    )

    today_loss = max(
        today_expense - today_income,
        Decimal("0")
    )


    monthly_profit = max(
        monthly_income - monthly_expense,
        Decimal("0")
    )

    monthly_loss = max(
        monthly_expense - monthly_income,
        Decimal("0")
    )


    total_profit = max(
        total_income - total_expense,
        Decimal("0")
    )

    total_loss = max(
        total_expense - total_income,
        Decimal("0")
    )


    yearly_profit = max(
        yearly_income - yearly_expense,
        Decimal("0")
    )

    yearly_loss = max(
        yearly_expense - yearly_income,
        Decimal("0")
    )


    # =====================================================
    # CATEGORY INCOME
    # =====================================================

    membership_income = (
        income_qs
        .filter(
            category="membership"
        )
        .aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0")
    )


    product_income = (
        sales_qs
        .aggregate(
            total=Sum("total_amount")
        )["total"]
        or Decimal("0")
    )


    admission_income = (
        income_qs
        .filter(
            category="other"
        )
        .aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0")
    )


    # =====================================================
    # GROWTH
    # =====================================================

    revenue_growth = calculate_growth(
        monthly_income,
        last_month_income
    )


    expense_growth = calculate_growth(
        monthly_expense,
        last_month_expense
    )


    previous_month_profit = (
        last_month_income
        - last_month_expense
    )


    profit_growth = calculate_growth(
        monthly_profit,
        previous_month_profit
    )


    sales_growth = calculate_growth(
        monthly_sales,
        last_month_sales
    )


    # =====================================================
    # RESPONSE
    # =====================================================

    return JsonResponse({

        # -----------------------------------------------
        # PERIOD
        # -----------------------------------------------

        "period": period,

        "start_date": start_date,

        "end_date": end_date,


        # -----------------------------------------------
        # MEMBERS
        # -----------------------------------------------

        "total_members": total_members,

        "active_members": active_members,

        "blocked_members": blocked_members,

        "expired_members": expired_members,

        "paused_members": paused_members,

        "pending_payments": pending_payments,


        # -----------------------------------------------
        # SELECTED PERIOD
        # -----------------------------------------------

        "total_income": period_income,

        "total_sales": period_sales,

        "total_expense": period_expense,

        "total_profit": period_profit,

        "period_loss": period_loss,


        # -----------------------------------------------
        # TODAY
        # -----------------------------------------------

        "today_income": today_income,

        "today_sales": today_sales,

        "today_expense": today_expense,

        "today_profit": today_profit,

        "today_loss": today_loss,


        # -----------------------------------------------
        # MONTHLY
        # -----------------------------------------------

        "monthly_income": monthly_income,

        "monthly_sales": monthly_sales,

        "monthly_expense": monthly_expense,

        "monthly_profit": monthly_profit,

        "monthly_loss": monthly_loss,


        # -----------------------------------------------
        # YEARLY
        # -----------------------------------------------

        "yearly_income": yearly_income,

        "yearly_sales": yearly_sales,

        "yearly_expense": yearly_expense,

        "yearly_profit": yearly_profit,

        "yearly_loss": yearly_loss,


        # -----------------------------------------------
        # ALL TIME
        # -----------------------------------------------

        "all_time_income": total_income,

        "all_time_sales": total_sales,

        "all_time_expense": total_expense,

        "all_time_profit": total_profit,

        "total_loss": total_loss,


        # -----------------------------------------------
        # CATEGORY INCOME
        # -----------------------------------------------

        "membership_income": membership_income,

        "product_income": product_income,

        "admission_income": admission_income,


        # -----------------------------------------------
        # GROWTH
        # -----------------------------------------------

        "sales_growth": sales_growth,

        "revenue_growth": revenue_growth,

        "expense_growth": expense_growth,

        "profit_growth": profit_growth,


        # -----------------------------------------------
        # UPCOMING EXPIRIES
        # -----------------------------------------------

        "upcoming_expiries": len(
            upcoming_expiries_list
        ),

        "upcoming_expiries_list":
            upcoming_expiries_list,


        # -----------------------------------------------
        # RECENT REGISTRATIONS
        # -----------------------------------------------

        "recent_registrations":
            recent_registrations,

    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_payments(request):
    tenant = get_tenant(request)

    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse(
            {"error": "Please select a tenant before viewing payments"},
            status=400
        )

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    # -----------------------------------------
    # Payment filtering
    # -----------------------------------------

    payments = (
        Payment.objects
        .filter(
            tenant=tenant
        )
        .select_related(
            "member",
            "member__plan",
            "member__branch"
        )
    )

    # BRANCH_ADMIN / STAFF → only own branch
    if request.user.role in ["BRANCH_ADMIN", "STAFF"]:

        if not request.user.branch_id:
            return JsonResponse(
                {"error": "User is not assigned to a branch"},
                status=403
            )

        payments = payments.filter(
            member__branch_id=request.user.branch_id
        )

    data = []

    for payment in payments:

        member = payment.member

        # -----------------------------------------
        # Calculate total paid for this member
        # -----------------------------------------

        total_paid = (
            Payment.objects
            .filter(
                tenant=tenant,
                member=member
            )
            .aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )

        # -----------------------------------------
        # Plan price
        # -----------------------------------------

        plan_fee = (
            member.plan.price
            if member.plan
            else 0
        )

        # -----------------------------------------
        # Remaining amount
        # -----------------------------------------

        due_amount = max(
            float(plan_fee) - float(total_paid),
            0
        )

        data.append({
            "id": payment.id,

            "member_id": member.id,

            "member_name": member.name,

            "amount_paid": payment.amount,

            "total_paid": total_paid,

            "due_amount": due_amount,

            "plan": (
                {
                    "id": member.plan.id,
                    "name": member.plan.name,
                    "price": member.plan.price,
                }
                if member.plan
                else None
            ),

            "branch": (
                {
                    "id": member.branch.id,
                    "name": member.branch.name,
                }
                if member.branch
                else None
            ),

            "payment_date": (
                payment.payment_date.isoformat()
                if payment.payment_date
                else None
            ),

            "payment_method": payment.payment_method,

            "payment_type": payment.payment_type,
        })

    return JsonResponse(data, safe=False)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def renew_member(request, member_id):

    tenant = get_tenant(request)

    # SUPER_ADMIN must select tenant
    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse(
            {"error": "Please select a tenant before renewing a member"},
            status=400
        )

    # Other users must belong to tenant
    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    # STAFF cannot renew
    if request.user.role == "STAFF":
        return JsonResponse(
            {"error": "Staff members are not allowed to renew members"},
            status=403
        )

    # Find member only inside tenant + allowed branch
    try:
        member = Member.objects.get(
            id=member_id,
            tenant=tenant,
            **get_branch_filter(request, tenant)
        )
    except Member.DoesNotExist:
        return JsonResponse(
            {"error": "Member not found or access denied"},
            status=404
        )

    # Get plan
    plan_id = request.POST.get("plan")

    if not plan_id:
        return JsonResponse(
            {"error": "Plan is required"},
            status=400
        )

    try:
        plan = Plan.objects.get(
            id=plan_id,
            tenant=tenant
        )
    except (Plan.DoesNotExist, ValueError):
        return JsonResponse(
            {"error": "Invalid plan"},
            status=400
        )

    duration = int(plan.duration)
    today = date.today()

    # Extend from current expiry if still active
    if member.expiry_date and member.expiry_date >= today:
        member.expiry_date = (
            member.expiry_date +
            timedelta(days=duration)
        )
    else:
        member.expiry_date = (
            today +
            timedelta(days=duration)
        )

    # IMPORTANT:
    # Member.plan is a ForeignKey
    member.plan = plan

    member.status = "Active"
    member.is_paused = False
    member.pause_start_date = None
    member.pause_expiry_date = None

    member.save()

    return JsonResponse({
        "message": "Plan renewed successfully",
        "member_id": member.id,
        "member_name": member.name,
        "plan": {
            "id": plan.id,
            "name": plan.name,
            "duration": plan.duration,
            "price": plan.price,
        },
        "new_expiry_date": member.expiry_date.isoformat(),
        "status": member.status,
    })



@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_blocked_members(request):

    tenant = get_tenant(request)

    # -------------------------------------------------
    # SUPER_ADMIN must select tenant
    # -------------------------------------------------

    if request.user.role == "SUPER_ADMIN" and tenant is None:

        return JsonResponse(
            {
                "error":
                    "Please select a tenant"
            },
            status=400
        )

    if tenant is None:

        return JsonResponse(
            {
                "error":
                    "User is not assigned to a tenant"
            },
            status=403
        )

    # -------------------------------------------------
    # Tenant + branch filtering
    # -------------------------------------------------

    members = Member.objects.filter(
        tenant=tenant,
        status="Blocked",
        **get_branch_filter(
            request,
            tenant
        )
    ).select_related(
        "plan",
        "branch"
    )

    data = [

        {
            "id": m.id,

            "name": m.name,

            "phone": m.phone,

            "plan": (
                {
                    "id": m.plan.id,
                    "name": m.plan.name,
                    "duration": m.plan.duration,
                    "price": m.plan.price,
                }
                if m.plan
                else None
            ),

            "branch": (
                {
                    "id": m.branch.id,
                    "name": m.branch.name,
                    "location": m.branch.location,
                }
                if m.branch
                else None
            ),

            "join_date": m.join_date,

            "expiry_date": (
                m.expiry_date.isoformat()
                if m.expiry_date
                else None
            ),

            "status": m.status,

            "photo": (
                m.photo.url
                if m.photo
                else None
            ),
        }

        for m in members
    ]

    return JsonResponse(
        data,
        safe=False
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def send_whatsapp(request, member_id):

    tenant = get_tenant(request)

    # SUPER_ADMIN must select tenant
    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse(
            {"error": "Please select a tenant before sending WhatsApp message"},
            status=400
        )

    # Other users must belong to tenant
    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    try:
        member = Member.objects.get(
            id=member_id,
            tenant=tenant,
            **get_branch_filter(request, tenant)
        )
    except Member.DoesNotExist:
        return JsonResponse(
            {"error": "Member not found or access denied"},
            status=404
        )

    return JsonResponse({
        "id": member.id,
        "name": member.name,
        "phone": member.phone,
        "due_amount": member.due_amount,
        "expiry_date": (
            member.expiry_date.isoformat()
            if member.expiry_date
            else None
        ),
    })



@api_view(["GET"])
@permission_classes([IsAuthenticated])
def expiring_soon_members(request):

    tenant = get_tenant(request)

    # SUPER_ADMIN must select tenant
    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse(
            {"error": "Please select a tenant before viewing expiring members"},
            status=400
        )

    # Other users must belong to tenant
    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    today = date.today()

    start_date = today - timedelta(days=5)
    end_date = today + timedelta(days=5)

    members = (
        Member.objects
        .filter(
            tenant=tenant,
            status="Active",
            expiry_date__gte=start_date,
            expiry_date__lte=end_date,
            **get_branch_filter(request, tenant)
        )
        .select_related(
            "plan",
            "branch"
        )
        .order_by("expiry_date")
    )

    data = [
        {
            "id": member.id,
            "name": member.name,
            "phone": member.phone,

            "expiry_date": (
                member.expiry_date.isoformat()
                if member.expiry_date
                else None
            ),

            "due_amount": member.due_amount,

            "days_left": (
                member.expiry_date - today
            ).days,

            "plan": (
                {
                    "id": member.plan.id,
                    "name": member.plan.name,
                    "price": member.plan.price,
                }
                if member.plan
                else None
            ),

            "branch": (
                {
                    "id": member.branch.id,
                    "name": member.branch.name,
                }
                if member.branch
                else None
            ),
        }
        for member in members
    ]

    return JsonResponse(
        data,
        safe=False
    )



@api_view(["GET"])
@permission_classes([IsAuthenticated])
def expired_members(request):

    tenant = get_tenant(request)

    # SUPER_ADMIN must select tenant
    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse(
            {"error": "Please select a tenant before viewing expired members"},
            status=400
        )

    # Other users must belong to tenant
    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    today = date.today()

    members = (
        Member.objects
        .filter(
            tenant=tenant,
            expiry_date__lt=today,
            **get_branch_filter(request, tenant)
        )
        .exclude(
            status__in=[
                "Paused",
                "Blocked"
            ]
        )
        .select_related(
            "plan",
            "branch"
        )
        .order_by("-expiry_date")
    )

    data = [
        {
            "id": member.id,

            "name": member.name,

            "phone": member.phone,

            "expiry_date": (
                member.expiry_date.isoformat()
                if member.expiry_date
                else None
            ),

            "status": member.status,

            "due_amount": member.due_amount,

            "plan": (
                {
                    "id": member.plan.id,
                    "name": member.plan.name,
                    "price": member.plan.price,
                }
                if member.plan
                else None
            ),

            "branch": (
                {
                    "id": member.branch.id,
                    "name": member.branch.name,
                }
                if member.branch
                else None
            ),
        }
        for member in members
    ]

    return JsonResponse(
        {
            "message": data
        }
    )



import json
from datetime import date, datetime, timedelta

from django.conf import settings
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from groq import Groq

from .models import (
    Member, Staffs, Payment, Expense, Income, Product, Sales_product,
    Enquiry, GymEquipment, MemberPause,
)
from .serializers import GymEquipmentSerializer
from .tenant_utils import get_tenant, get_branch_filter


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_product(request):

    tenant = get_tenant(request)

    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse(
            {"error": "Please select a tenant before creating a product"},
            status=400
        )

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    if request.user.role not in ["SUPER_ADMIN", "TENANT_ADMIN"]:
        return JsonResponse(
            {"error": "Only tenant admins can create products"},
            status=403
        )

    product = Product.objects.create(
        tenant=tenant,
        name=request.POST.get("name"),
        description=request.POST.get("description"),
        price=request.POST.get("price"),
        stock=request.POST.get("stock"),
        category=request.POST.get("category"),
        image=request.FILES.get("image"),
    )

    return JsonResponse(
        {
            "message": "Product created",
            "id": product.id
        },
        status=201
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_products(request):

    tenant = get_tenant(request)

    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse(
            {"error": "Please select a tenant before viewing products"},
            status=400
        )

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    products = (
        Product.objects
        .filter(tenant=tenant)
        .order_by("id")
    )

    data = [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "price": p.price,
            "stock": p.stock,
            "category": p.category,
            "image": p.image.url if p.image else None,
        }
        for p in products
    ]

    return JsonResponse(data, safe=False)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def update_product(request, product_id):

    tenant = get_tenant(request)

    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse(
            {"error": "Please select a tenant before updating a product"},
            status=400
        )

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    if request.user.role not in ["SUPER_ADMIN", "TENANT_ADMIN"]:
        return JsonResponse(
            {"error": "Only tenant admins can update products"},
            status=403
        )

    try:
        product = Product.objects.get(
            id=product_id,
            tenant=tenant
        )
    except Product.DoesNotExist:
        return JsonResponse(
            {"error": "Product not found"},
            status=404
        )

    product.name = request.POST.get(
        "name",
        product.name
    )

    product.description = request.POST.get(
        "description",
        product.description
    )

    product.price = request.POST.get(
        "price",
        product.price
    )

    product.stock = request.POST.get(
        "stock",
        product.stock
    )

    product.category = request.POST.get(
        "category",
        product.category
    )

    if request.FILES.get("image"):
        product.image = request.FILES.get("image")

    product.save()

    return JsonResponse(
        {"message": "Product updated successfully"},
        status=200
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_product(request, product_id):

    tenant = get_tenant(request)

    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse(
            {"error": "Please select a tenant before deleting a product"},
            status=400
        )

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    if request.user.role not in ["SUPER_ADMIN", "TENANT_ADMIN"]:
        return JsonResponse(
            {"error": "Not permitted"},
            status=403
        )

    try:
        product = Product.objects.get(
            id=product_id,
            tenant=tenant
        )
    except Product.DoesNotExist:
        return JsonResponse(
            {"error": "Product not found"},
            status=404
        )

    product.delete()

    return JsonResponse(
        {"message": "Product deleted successfully"},
        status=200
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def sales_list(request):

    tenant = get_tenant(request)

    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse(
            {"error": "Please select a tenant before viewing sales"},
            status=400
        )

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    period = request.GET.get(
        "period",
        "daily"
    ).lower()

    selected_date = request.GET.get("date")

    start_date, end_date = get_period_dates(
        period,
        selected_date
    )

    if start_date is None:
        return JsonResponse(
            {"error": "Invalid period"},
            status=400
        )

    sales = (
        Sales_product.objects
        .filter(
            tenant=tenant,
            sold_at__date__gte=start_date,
            sold_at__date__lte=end_date
        )
        .select_related(
            "product",
            "member",
            "member__branch"
        )
    )

    # -----------------------------------------
    # Branch restriction
    # -----------------------------------------

    if request.user.role in ["BRANCH_ADMIN", "STAFF"]:

        if not request.user.branch_id:
            return JsonResponse(
                {"error": "User is not assigned to a branch"},
                status=403
            )

        sales = sales.filter(
            member__branch_id=request.user.branch_id
        )

    sales = sales.order_by("-sold_at")

    data = [
        {
            "id": sale.id,

            "member_id": (
                sale.member.id
                if sale.member
                else None
            ),

            "member_name": (
                sale.member.name
                if sale.member
                else None
            ),

            "product": sale.product.name,

            "category": sale.product.category,

            "quantity": sale.quantity,

            "payment_method": sale.payment_method,

            "unit_price": float(
                sale.unit_price
            ),

            "total_amount": float(
                sale.total_amount
            ),

            "sold_at": sale.sold_at.strftime(
                "%d-%m-%Y %H:%M"
            ),

            "branch": (
                {
                    "id": sale.member.branch.id,
                    "name": sale.member.branch.name,
                }
                if sale.member and sale.member.branch
                else None
            ),
        }
        for sale in sales
    ]

    return JsonResponse(
        {
            "success": True,
            "period": period,
            "start_date": start_date,
            "end_date": end_date,
            "sales": data
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def one_sale(request, sale_id):
    tenant = get_tenant(request)
    sale = get_object_or_404(Sales_product, id=sale_id, tenant=tenant)

    return JsonResponse({
        "id": sale.id,
        "member_id": sale.member_id,
        "member_name": sale.member.name,
        "product": getattr(sale.product, "name", str(sale.product)),
        "quantity": sale.quantity,
        "unit_price": float(sale.unit_price),
        "total_amount": float(sale.total_amount),
        "payment_method": sale.payment_method,
        "sold_at": sale.sold_at,
        "invoice_no": getattr(sale, "invoice_no", f"INV-{sale.id}"),
    })



# ============================================================
# STAFF
# ============================================================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_staff(request):

    # Only BRANCH_ADMIN can create staff
    if request.user.role != "BRANCH_ADMIN":
        return JsonResponse(
            {"error": "Only Branch Admin can create staff"},
            status=403
        )

    tenant = get_tenant(request)

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    # Branch Admin must have a branch
    if not request.user.branch_id:
        return JsonResponse(
            {"error": "You are not assigned to a branch"},
            status=403
        )

    # Automatically use the logged-in admin's branch
    try:
        branch = Branch.objects.get(
            id=request.user.branch_id,
            tenant=tenant
        )
    except Branch.DoesNotExist:
        return JsonResponse(
            {"error": "Invalid branch assignment"},
            status=403
        )

    phone = request.POST.get("phone")

    if not phone or not (
        phone.isdigit() and len(phone) == 10
    ):
        return JsonResponse(
            {"error": "Enter a valid 10-digit mobile number"},
            status=400
        )

    staff = Staffs.objects.create(
        tenant=tenant,
        branch=branch,
        name=request.POST.get("name"),
        role=request.POST.get("role"),
        specialization=request.POST.get("specialization"),
        phone=phone,
        experience=request.POST.get("experience"),
        joining_date=request.POST.get("joining_date"),
        salary=request.POST.get("salary"),
        status=request.POST.get("status") or "Active",
    )

    return JsonResponse(
        {
            "id": staff.id,
            "name": staff.name,
            "status": staff.status,
            "branch": {
                "id": branch.id,
                "name": branch.name,
            },
        },
        status=201
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_staffs(request):

    tenant = get_tenant(request)

    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse(
            {"error": "Please select a tenant before viewing staff"},
            status=400
        )

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    staffs = (
        Staffs.objects
        .filter(tenant=tenant)
        .select_related("branch")
        .order_by("-id")
    )

    # Branch users → own branch only
    if request.user.role in ["BRANCH_ADMIN", "STAFF"]:

        if not request.user.branch_id:
            return JsonResponse(
                {"error": "User is not assigned to a branch"},
                status=403
            )

        staffs = staffs.filter(
            branch_id=request.user.branch_id
        )

    data = []

    for staff in staffs:

        paid_amount = (
            Payment.objects
            .filter(
                tenant=tenant,
                staff=staff,
                payment_type="Salary"
            )
            .aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )

        data.append({
            "id": staff.id,
            "name": staff.name,
            "role": staff.role,
            "specialization": staff.specialization,
            "phone": staff.phone,
            "experience": staff.experience,
            "joining_date": staff.joining_date,
            "salary": str(staff.salary),
            "paid_amount": str(paid_amount),
            "status": staff.status,

            "branch": (
                {
                    "id": staff.branch.id,
                    "name": staff.branch.name,
                }
                if staff.branch
                else None
            ),
        })

    return JsonResponse(
        data,
        safe=False
    )

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_staff(request, staff_id):

    tenant = get_tenant(request)

    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse(
            {"error": "Please select a tenant before viewing staff"},
            status=400
        )

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    try:
        staff = (
            Staffs.objects
            .select_related("branch")
            .get(
                id=staff_id,
                tenant=tenant
            )
        )
    except Staffs.DoesNotExist:
        return JsonResponse(
            {"error": "Staff not found"},
            status=404
        )

    # Branch restriction
    if request.user.role in ["BRANCH_ADMIN", "STAFF"]:

        if staff.branch_id != request.user.branch_id:
            return JsonResponse(
                {"error": "You are not permitted to access this staff member"},
                status=403
            )

    paid_amount = (
        Payment.objects
        .filter(
            tenant=tenant,
            staff=staff,
            payment_type="Salary"
        )
        .aggregate(
            total=Sum("amount")
        )["total"]
        or 0
    )

    return JsonResponse({
        "id": staff.id,
        "name": staff.name,
        "role": staff.role,
        "specialization": staff.specialization,
        "phone": staff.phone,
        "experience": staff.experience,
        "joining_date": staff.joining_date,
        "salary": str(staff.salary),
        "paid_amount": str(paid_amount),
        "status": staff.status,

        "branch": (
            {
                "id": staff.branch.id,
                "name": staff.branch.name,
            }
            if staff.branch
            else None
        ),
    })

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def update_staff(request, id):

    tenant = get_tenant(request)

    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse(
            {"error": "Please select a tenant before updating staff"},
            status=400
        )

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    if request.user.role not in ["SUPER_ADMIN", "TENANT_ADMIN"]:
        return JsonResponse(
            {"error": "Only tenant admins can update staff"},
            status=403
        )

    try:
        staff = Staffs.objects.get(
            id=id,
            tenant=tenant
        )
    except Staffs.DoesNotExist:
        return JsonResponse(
            {"success": False, "error": "Staff not found"},
            status=404
        )

    branch_id = request.POST.get(
        "branch",
        staff.branch_id
    )

    try:
        branch = Branch.objects.get(
            id=branch_id,
            tenant=tenant
        )
    except (Branch.DoesNotExist, ValueError):
        return JsonResponse(
            {"error": "Invalid branch"},
            status=400
        )

    staff.name = request.POST.get("name", staff.name)
    staff.role = request.POST.get("role", staff.role)
    staff.specialization = request.POST.get(
        "specialization",
        staff.specialization
    )
    staff.phone = request.POST.get(
        "phone",
        staff.phone
    )
    staff.experience = request.POST.get(
        "experience",
        staff.experience
    )
    staff.joining_date = request.POST.get(
        "joining_date",
        staff.joining_date
    )
    staff.salary = request.POST.get(
        "salary",
        staff.salary
    )
    staff.status = request.POST.get(
        "status",
        staff.status
    )
    staff.branch = branch

    staff.save()

    return JsonResponse({
        "success": True,
        "message": "Staff updated successfully"
    })

@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_staff(request, staff_id):

    tenant = get_tenant(request)

    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse(
            {"error": "Please select a tenant before deleting staff"},
            status=400
        )

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    if request.user.role not in ["SUPER_ADMIN", "TENANT_ADMIN"]:
        return JsonResponse(
            {"error": "Not permitted"},
            status=403
        )

    try:
        staff = Staffs.objects.get(
            id=staff_id,
            tenant=tenant
        )
    except Staffs.DoesNotExist:
        return JsonResponse(
            {"error": "Staff not found"},
            status=404
        )

    staff.delete()

    return JsonResponse(
        {"message": "Staff deleted successfully"},
        status=200
    )


# ============================================================
# PAUSE / RESUME
# ============================================================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def pause_member(request, member_id):
    tenant = get_tenant(request)

    # SUPER_ADMIN must select a tenant
    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse({
            "error": "Please select a tenant before pausing a member"
        }, status=400)

    if tenant is None:
        return JsonResponse({
            "error": "User is not assigned to a tenant"
        }, status=403)

    # STAFF cannot pause members
    if request.user.role == "STAFF":
        return JsonResponse({
            "error": "Staff members are not allowed to pause members"
        }, status=403)

    try:
        member = Member.objects.get(
            id=member_id,
            tenant=tenant,
            **get_branch_filter(request, tenant)
        )
    except Member.DoesNotExist:
        return JsonResponse({
            "error": "Member not found or access denied"
        }, status=404)

    if member.is_paused:
        return JsonResponse({
            "success": False,
            "message": "Member already paused",
            "paused_date": (
                member.pause_start_date.strftime("%Y-%m-%d")
                if member.pause_start_date else None
            ),
        }, status=400)

    # Parse request body
    try:
        body = json.loads(request.body)
        freeze_date = datetime.strptime(
            body["freeze_date"],
            "%Y-%m-%d"
        ).date()
    except (KeyError, ValueError, json.JSONDecodeError):
        return JsonResponse({
            "success": False,
            "error": "Valid freeze_date is required (YYYY-MM-DD)"
        }, status=400)

    # Calculate month range
    month_start = freeze_date.replace(day=1)

    if freeze_date.month == 12:
        next_month = freeze_date.replace(
            year=freeze_date.year + 1,
            month=1,
            day=1
        )
    else:
        next_month = freeze_date.replace(
            month=freeze_date.month + 1,
            day=1
        )

    month_end = next_month - timedelta(days=1)

    # Maximum 2 pauses per month
    pause_count = MemberPause.objects.filter(
        tenant=tenant,
        member=member,
        start_date__gte=month_start,
        start_date__lte=month_end
    ).count()

    if pause_count >= 2:
        return JsonResponse({
            "success": False,
            "error": "Maximum 2 pauses are allowed per month.",
            "pause_count": pause_count,
            "max_pauses": 2
        }, status=400)

    # Calculate used pause days
    previous_pauses = MemberPause.objects.filter(
        tenant=tenant,
        member=member,
        start_date__gte=month_start,
        start_date__lte=month_end,
        end_date__isnull=False
    )

    used_days = sum(
        pause.paused_days
        for pause in previous_pauses
    )

    remaining_days = max(0, 15 - used_days)

    if remaining_days <= 0:
        return JsonResponse({
            "success": False,
            "error": "Member has already used the maximum 15 pause days this month.",
            "used_days": used_days,
            "remaining_days": 0,
            "max_pause_days": 15
        }, status=400)

    allowed_days = remaining_days

    allowed_resume_date = (
        freeze_date + timedelta(days=allowed_days)
    )

    # Create pause record
    pause = MemberPause.objects.create(
        tenant=tenant,
        member=member,
        start_date=freeze_date,
        allowed_days=allowed_days,
        paused_days=0
    )

    # Update member
    member.is_paused = True
    member.pause_start_date = freeze_date
    member.pause_expiry_date = allowed_resume_date
    member.status = "Paused"
    member.used_pause_days = used_days
    member.save()

    return JsonResponse({
        "success": True,
        "message": "Member paused successfully",
        "pause_id": pause.id,

        "pause_start_date": freeze_date.strftime("%Y-%m-%d"),

        "pause_days_used": used_days,
        "pause_days_remaining": remaining_days,

        "pause_count": pause_count + 1,
        "allowed_days": allowed_days,

        "allowed_resume_date": (
            allowed_resume_date.strftime("%Y-%m-%d")
        ),

        "status": member.status,
        "is_paused": member.is_paused,
    })

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def resume_member(request, member_id):
    tenant = get_tenant(request)

    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse({
            "error": "Please select a tenant before resuming a member"
        }, status=400)

    if tenant is None:
        return JsonResponse({
            "error": "User is not assigned to a tenant"
        }, status=403)

    # STAFF cannot resume
    if request.user.role == "STAFF":
        return JsonResponse({
            "error": "Staff members are not allowed to resume members"
        }, status=403)

    try:
        member = Member.objects.get(
            id=member_id,
            tenant=tenant,
            **get_branch_filter(request, tenant)
        )
    except Member.DoesNotExist:
        return JsonResponse({
            "error": "Member not found or access denied"
        }, status=404)

    if not member.is_paused:
        return JsonResponse({
            "success": False,
            "message": "Member is not paused"
        }, status=400)

    # Parse resume date
    try:
        body = json.loads(request.body)

        resume_date = datetime.strptime(
            body["resume_date"],
            "%Y-%m-%d"
        ).date()

    except (KeyError, ValueError, json.JSONDecodeError):
        return JsonResponse({
            "success": False,
            "error": "Valid resume_date is required (YYYY-MM-DD)"
        }, status=400)

    # Find active pause
    pause = (
        MemberPause.objects
        .filter(
            tenant=tenant,
            member=member,
            end_date__isnull=True
        )
        .order_by("-start_date")
        .first()
    )

    if not pause:
        return JsonResponse({
            "success": False,
            "error": "Active pause record not found."
        }, status=400)

    pause_start = pause.start_date

    paused_days = (
        resume_date - pause_start
    ).days

    if paused_days <= 0:
        return JsonResponse({
            "success": False,
            "error": "Resume date must be after pause date."
        }, status=400)

    if paused_days > pause.allowed_days:
        return JsonResponse({
            "success": False,
            "error": "Pause limit exceeded.",
            "allowed_days": pause.allowed_days,
            "requested_days": paused_days,
            "max_monthly_days": 15
        }, status=400)

    # Close pause
    pause.end_date = resume_date
    pause.paused_days = paused_days
    pause.save()

    # Extend membership expiry
    if member.expiry_date:
        member.expiry_date += timedelta(
            days=paused_days
        )

    # Calculate monthly pause usage
    month_start = pause_start.replace(day=1)

    if pause_start.month == 12:
        next_month = pause_start.replace(
            year=pause_start.year + 1,
            month=1,
            day=1
        )
    else:
        next_month = pause_start.replace(
            month=pause_start.month + 1,
            day=1
        )

    month_end = next_month - timedelta(days=1)

    completed_pauses = MemberPause.objects.filter(
        tenant=tenant,
        member=member,
        start_date__gte=month_start,
        start_date__lte=month_end,
        end_date__isnull=False
    )

    used_days_this_month = sum(
        p.paused_days
        for p in completed_pauses
    )

    # Update member
    member.is_paused = False
    member.pause_start_date = None
    member.pause_expiry_date = None
    member.status = "Active"
    member.used_pause_days = used_days_this_month
    member.save()

    return JsonResponse({
        "success": True,
        "message": "Member resumed successfully",

        "paused_days": paused_days,

        "used_days_this_month": used_days_this_month,

        "remaining_days_this_month": max(
            0,
            15 - used_days_this_month
        ),

        "new_expiry_date": (
            member.expiry_date.strftime("%Y-%m-%d")
            if member.expiry_date else None
        ),

        "status": member.status,
        "is_paused": member.is_paused,
    })

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_member_payment(request, member_id):
    tenant = get_tenant(request)

    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse({
            "error": "Please select a tenant before recording payment"
        }, status=400)

    if tenant is None:
        return JsonResponse({
            "error": "User is not assigned to a tenant"
        }, status=403)

    try:
        member = Member.objects.get(
            id=member_id,
            tenant=tenant,
            **get_branch_filter(request, tenant)
        )
    except Member.DoesNotExist:
        return JsonResponse({
            "error": "Member not found or access denied"
        }, status=404)

    # Parse JSON
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({
            "error": "Invalid JSON data"
        }, status=400)

    # Amount
    try:
        amount = float(data.get("amount", 0))
    except (ValueError, TypeError):
        return JsonResponse({
            "error": "Invalid payment amount"
        }, status=400)

    if amount <= 0:
        return JsonResponse({
            "error": "Amount must be greater than 0"
        }, status=400)

    current_due = float(member.due_amount or 0)

    if current_due <= 0:
        return JsonResponse({
            "error": "Membership fee already fully paid"
        }, status=400)

    if amount > current_due:
        return JsonResponse({
            "error": f"Amount cannot exceed due amount ₹{current_due}"
        }, status=400)

    payment_method = data.get(
        "payment_method",
        "cash"
    )

    # Create income transaction
    income = Income.objects.create(
        tenant=tenant,
        member=member,
        title="Membership",
        name=member.name,
        phone=member.phone,
        category="membership",
        amount=amount,
        payment_method=payment_method,
        description=(
            f"Membership payment received from {member.name}"
        ),
        is_system_generated=True,
    )

    # Update member payment information
    member.paid_amount = (
        float(member.paid_amount or 0) + amount
    )

    member.due_amount = max(
        current_due - amount,
        0
    )

    member.save()

    return JsonResponse({
        "message": "Member payment recorded",

        "income_id": income.id,

        "member_id": member.id,
        "member_name": member.name,

        "paid_amount": member.paid_amount,
        "due_amount": member.due_amount,

        "payment_completed": (
            float(member.due_amount) == 0
        ),
    }, status=201)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_staff_payment(request, staff_id):
    tenant = get_tenant(request)

    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse({
            "error": "Please select a tenant before recording staff payment"
        }, status=400)

    if tenant is None:
        return JsonResponse({
            "error": "User is not assigned to a tenant"
        }, status=403)

    # Only admins can pay staff
    if request.user.role not in [
        "SUPER_ADMIN",
        "TENANT_ADMIN"
    ]:
        return JsonResponse({
            "error": "Only Super Admin and Tenant Admin can record staff payments"
        }, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({
            "error": "Invalid JSON data"
        }, status=400)

    # Get staff belonging to selected tenant
    try:
        staff = (
            Staffs.objects
            .select_related("branch")
            .get(
                id=staff_id,
                tenant=tenant
            )
        )
    except Staffs.DoesNotExist:
        return JsonResponse({
            "error": "Staff not found or access denied"
        }, status=404)

    # Amount
    try:
        amount = float(data.get("amount", 0))
    except (ValueError, TypeError):
        return JsonResponse({
            "error": "Invalid payment amount"
        }, status=400)

    if amount <= 0:
        return JsonResponse({
            "error": "Amount must be greater than 0"
        }, status=400)

    payment_date = data.get("payment_date")

    if not payment_date:
        return JsonResponse({
            "error": "Payment date is required"
        }, status=400)

    payment_method = data.get("payment_method")

    if not payment_method:
        return JsonResponse({
            "error": "Payment method is required"
        }, status=400)

    payment_type = data.get(
        "payment_type",
        "Salary"
    )

    description = data.get(
        "description",
        ""
    )

    # Create payment record
    payment = Payment.objects.create(
        tenant=tenant,
        staff=staff,
        amount=amount,
        payment_type=payment_type,
        payment_method=payment_method,
        payment_date=payment_date,
    )

    # Create expense record
    expense = Expense.objects.create(
        tenant=tenant,
        title=payment_type,
        name=staff.name,
        phone=staff.phone,
        category="salary",
        amount=amount,
        payment_method=payment_method,
        date=payment_date,
        description=(
            description
            or f"{payment_type} paid to {staff.name}"
        ),
        is_system_generated=True,
    )

    return JsonResponse({
        "message": "Staff payment recorded successfully",

        "payment_id": payment.id,
        "expense_id": expense.id,

        "staff_id": staff.id,
        "staff_name": staff.name,

        "amount": str(payment.amount),
        "payment_type": payment_type,

        "branch": {
            "id": staff.branch.id,
            "name": staff.branch.name
        } if staff.branch else None,
    }, status=201)
    

# ============================================================
# ENQUIRY
# ============================================================

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_enquiry(request):
    tenant = get_tenant(request)

    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse({
            "error": "Please select a tenant before adding an enquiry"
        }, status=400)

    if tenant is None:
        return JsonResponse({
            "error": "User is not assigned to a tenant"
        }, status=403)

    name = request.POST.get("name")
    phone = request.POST.get("phone")
    plan = request.POST.get("plan")
    edate = request.POST.get("date")

    if not name:
        return JsonResponse({
            "error": "Name is required"
        }, status=400)

    if not (phone and phone.isdigit() and len(phone) == 10):
        return JsonResponse({
            "error": "Enter a valid 10-digit mobile number"
        }, status=400)

    enquiry = Enquiry.objects.create(
        tenant=tenant,
        name=name,
        phone=phone,
        plan=plan,
        date=edate
    )

    return JsonResponse({
        "message": "Enquiry added",
        "id": enquiry.id,
        "name": enquiry.name,
        "phone": enquiry.phone,
        "plan": enquiry.plan,
        "date": enquiry.date
    }, status=201)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def view_enquiry(request):
    tenant = get_tenant(request)

    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse({
            "error": "Please select a tenant before viewing enquiries"
        }, status=400)

    if tenant is None:
        return JsonResponse({
            "error": "User is not assigned to a tenant"
        }, status=403)

    enquiries = (
        Enquiry.objects
        .filter(tenant=tenant)
        .order_by("-id")
    )

    data = [
        {
            "id": e.id,
            "name": e.name,
            "phone": e.phone,
            "plan": e.plan,
            "date": e.date,
        }
        for e in enquiries
    ]

    return JsonResponse(data, safe=False)

@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_enquiry(request, enquiry_id):
    tenant = get_tenant(request)

    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse({
            "error": "Please select a tenant before deleting an enquiry"
        }, status=400)

    if tenant is None:
        return JsonResponse({
            "error": "User is not assigned to a tenant"
        }, status=403)

    if request.user.role not in [
        "SUPER_ADMIN",
        "TENANT_ADMIN",
        "BRANCH_ADMIN"
    ]:
        return JsonResponse({
            "error": "You are not allowed to delete enquiries"
        }, status=403)

    enquiry = get_object_or_404(
        Enquiry,
        id=enquiry_id,
        tenant=tenant
    )

    enquiry.delete()

    return JsonResponse({
        "message": "Enquiry deleted successfully"
    })


# ============================================================
# EXPENSES / INCOME (manual entries + reports)
# ============================================================

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_expense(request):
    tenant = get_tenant(request)

    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse({
            "error": "Please select a tenant before adding an expense"
        }, status=400)

    if tenant is None:
        return JsonResponse({
            "error": "User is not assigned to a tenant"
        }, status=403)

    if request.user.role not in [
        "SUPER_ADMIN",
        "TENANT_ADMIN"
    ]:
        return JsonResponse({
            "error": "Only Super Admin and Tenant Admin can add expenses"
        }, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({
            "error": "Invalid JSON data"
        }, status=400)

    try:
        amount = float(data.get("amount", 0))
    except (ValueError, TypeError):
        return JsonResponse({
            "error": "Invalid expense amount"
        }, status=400)

    if amount <= 0:
        return JsonResponse({
            "error": "Amount must be greater than 0"
        }, status=400)

    expense = Expense.objects.create(
        tenant=tenant,
        title=data.get("title"),
        name=data.get("name"),
        phone=data.get("phone"),
        category=data.get("category"),
        description=data.get("description"),
        amount=amount,
        payment_method=data.get("payment_method"),
        date=data.get("date"),
        is_system_generated=False,
    )

    return JsonResponse({
        "message": "Expense added successfully",
        "id": expense.id
    }, status=201)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def view_expenses(request):
    tenant = get_tenant(request)

    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse({
            "error": "Please select a tenant before viewing expenses"
        }, status=400)

    if tenant is None:
        return JsonResponse({
            "error": "User is not assigned to a tenant"
        }, status=403)

    qs = (
        Expense.objects
        .filter(tenant=tenant)
        .order_by("-date", "-id")
    )

    data = [
        {
            "id": e.id,
            "title": e.title,
            "name": e.name,
            "phone": e.phone,
            "category": e.category,
            "description": e.description,
            "amount": str(e.amount),
            "payment_method": e.payment_method,
            "date": e.date.strftime("%Y-%m-%d"),
            "type": (
                "Salary"
                if e.is_system_generated
                else "Additional"
            ),
        }
        for e in qs
    ]

    return JsonResponse(data, safe=False)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_income(request):
    tenant = get_tenant(request)

    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse({
            "error": "Please select a tenant before adding income"
        }, status=400)

    if tenant is None:
        return JsonResponse({
            "error": "User is not assigned to a tenant"
        }, status=403)

    if request.user.role not in [
        "SUPER_ADMIN",
        "TENANT_ADMIN"
    ]:
        return JsonResponse({
            "error": "Only Super Admin and Tenant Admin can add income"
        }, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({
            "error": "Invalid JSON data"
        }, status=400)

    member = None

    if data.get("member_id"):
        try:
            member = Member.objects.get(
                id=data.get("member_id"),
                tenant=tenant,
                **get_branch_filter(request, tenant)
            )
        except Member.DoesNotExist:
            return JsonResponse({
                "error": "Member not found or access denied"
            }, status=404)

    try:
        amount = float(data.get("amount", 0))
    except (ValueError, TypeError):
        return JsonResponse({
            "error": "Invalid income amount"
        }, status=400)

    if amount <= 0:
        return JsonResponse({
            "error": "Amount must be greater than 0"
        }, status=400)

    income = Income.objects.create(
        tenant=tenant,
        member=member,
        title=data.get("title"),
        name=data.get("name"),
        phone=data.get("phone"),
        category=data.get("category"),
        description=data.get("description"),
        amount=amount,
        payment_method=data.get("payment_method", "cash"),
        date=data.get("date"),
        is_system_generated=False,
    )

    return JsonResponse({
        "message": "Additional income added successfully",
        "income_id": income.id
    }, status=201)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def incomes(request):
    tenant = get_tenant(request)

    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse({
            "error": "Please select a tenant before viewing income"
        }, status=400)

    if tenant is None:
        return JsonResponse({
            "error": "User is not assigned to a tenant"
        }, status=403)

    data = []

    # -------------------------
    # INCOME
    # -------------------------

    income_qs = (
        Income.objects
        .filter(tenant=tenant)
        .select_related("member", "member__branch")
        .order_by("-date", "-id")
    )

    # Branch-level filtering
    if request.user.role in [
        "BRANCH_ADMIN",
        "STAFF"
    ]:
        if not request.user.branch_id:
            return JsonResponse({
                "error": "User is not assigned to a branch"
            }, status=403)

        income_qs = income_qs.filter(
            member__branch_id=request.user.branch_id
        )

    for income in income_qs:
        data.append({
            "id": f"in_{income.id}",
            "title": income.title,
            "name": income.name,
            "phone": income.phone,
            "category": income.category,
            "description": income.description,
            "amount": str(income.amount),
            "payment_method": income.payment_method,
            "date": income.date.strftime("%Y-%m-%d"),
            "type": (
                "Membership"
                if income.is_system_generated
                else "Additional"
            ),
            "_sort_date": income.date,
        })

    # -------------------------
    # PRODUCT SALES
    # -------------------------

    sales_qs = (
        Sales_product.objects
        .filter(tenant=tenant)
        .select_related(
            "member",
            "member__branch",
            "product"
        )
        .order_by("-sold_at", "-id")
    )

    # Branch-level filtering
    if request.user.role in [
        "BRANCH_ADMIN",
        "STAFF"
    ]:
        sales_qs = sales_qs.filter(
            member__branch_id=request.user.branch_id
        )

    for sale in sales_qs:
        data.append({
            "id": f"sa_{sale.id}",
            "title": "Product Sale",
            "name": sale.product.name,
            "phone": (
                sale.member.phone
                if sale.member else ""
            ),
            "category": "Product",
            "description": (
                f"{sale.product.name} × {sale.quantity}"
            ),
            "amount": str(sale.total_amount),
            "payment_method": sale.payment_method,
            "date": sale.sold_at.strftime("%Y-%m-%d"),
            "type": "Product Sale",
            "_sort_date": sale.sold_at,
        })

    # Sort everything together
    data.sort(
        key=lambda x: x["_sort_date"],
        reverse=True
    )

    for item in data:
        item.pop("_sort_date", None)

    return JsonResponse(data, safe=False)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def income_by_members(request):
    tenant = get_tenant(request)

    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse({
            "error": "Please select a tenant before viewing income"
        }, status=400)

    if tenant is None:
        return JsonResponse({
            "error": "User is not assigned to a tenant"
        }, status=403)

    period = request.GET.get(
        "period",
        "daily"
    ).lower()

    selected_date = request.GET.get("date")

    start_date, end_date = get_period_dates(
        period,
        selected_date
    )

    if start_date is None:
        return JsonResponse({
            "error": "Invalid period"
        }, status=400)

    base_income = (
        Income.objects
        .filter(
            tenant=tenant,
            date__date__gte=start_date,
            date__date__lte=end_date
        )
        .select_related(
            "member",
            "member__plan",
            "member__branch"
        )
    )

    # Branch restriction
    if request.user.role in [
        "BRANCH_ADMIN",
        "STAFF"
    ]:
        if not request.user.branch_id:
            return JsonResponse({
                "error": "User is not assigned to a branch"
            }, status=403)

        base_income = base_income.filter(
            member__branch_id=request.user.branch_id
        )

    # Plan is now a ForeignKey
    basic_income = (
        base_income
        .filter(
            category="membership",
            member__plan__name__in=[
                "Silver",
                "Gold"
            ]
        )
        .aggregate(
            total=Sum("amount")
        )["total"] or 0
    )

    premium_income = (
        base_income
        .filter(
            category="membership",
            member__plan__name__in=[
                "Premium",
                "Platinum"
            ]
        )
        .aggregate(
            total=Sum("amount")
        )["total"] or 0
    )

    other_income = (
        base_income
        .filter(
            category__in=[
                "registration",
                "product_sale",
                "other"
            ]
        )
        .aggregate(
            total=Sum("amount")
        )["total"] or 0
    )

    return JsonResponse({
        "success": True,
        "period": period,
        "start_date": start_date,
        "end_date": end_date,

        "income": [
            {
                "name": "Basic",
                "amount": float(basic_income)
            },
            {
                "name": "Premium",
                "amount": float(premium_income)
            },
            {
                "name": "Other",
                "amount": float(other_income)
            },
        ],
    })

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def expense_by_category(request):
    tenant = get_tenant(request)

    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse(
            {"error": "Please select a tenant before viewing expenses"},
            status=400
        )

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    period = request.GET.get("period", "daily").lower()
    selected_date = request.GET.get("date")

    start_date, end_date = get_period_dates(period, selected_date)

    if start_date is None:
        return JsonResponse(
            {"error": "Invalid period"},
            status=400
        )

    expenses = Expense.objects.filter(
        tenant=tenant,
        date__gte=start_date,
        date__lte=end_date
    )

    # Current Expense model has no branch field.
    # Therefore branch users cannot be isolated correctly here yet.
    if request.user.role in ["BRANCH_ADMIN", "STAFF"]:
        return JsonResponse(
            {
                "error": "Branch-level expense filtering requires a branch field on Expense."
            },
            status=400
        )

    qs = (
        expenses
        .values("category")
        .annotate(total=Sum("amount"))
        .order_by("-total")
    )

    data = [
        {
            "category": expense["category"],
            "amount": float(expense["total"] or 0)
        }
        for expense in qs
    ]

    return JsonResponse({
        "success": True,
        "period": period,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "expenses": data,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def profit_loss_report(request):
    tenant = get_tenant(request)
    period = request.GET.get("period")
    selected_date = request.GET.get("date")
    from_date = request.GET.get("from_date")
    to_date = request.GET.get("to_date")

    if from_date and to_date:
        start_date = datetime.strptime(from_date, "%Y-%m-%d").date()
        end_date = datetime.strptime(to_date, "%Y-%m-%d").date()
    else:
        start_date, end_date = get_period_dates(period, selected_date)

    if start_date is None:
        return JsonResponse({"error": "Invalid period"}, status=400)

    incomes_qs = Income.objects.filter(tenant=tenant, date__gte=start_date, date__lte=end_date)
    income_members = []
    total_membership_income = 0
    for income in incomes_qs:
        amount = float(income.amount)
        total_membership_income += amount
        income_members.append({
            "member": income.member.name if income.member else "-", "amount": amount,
            "payment_method": income.payment_method, "date": income.date.strftime("%d-%m-%Y"),
        })

    sales_qs = Sales_product.objects.filter(tenant=tenant).select_related("member", "product").filter(
        sold_at__date__gte=start_date, sold_at__date__lte=end_date
    )
    sales_list_data = []
    sales_category = {}
    total_sales = 0
    for sale in sales_qs:
        amount = float(sale.total_amount)
        total_sales += amount
        category = sale.product.category or "Other"
        sales_category[category] = sales_category.get(category, 0) + amount
        sales_list_data.append({
            "member": sale.member.name if sale.member else "-", "product": sale.product.name,
            "category": category, "quantity": sale.quantity, "amount": amount,
            "date": sale.sold_at.strftime("%d-%m-%Y %H:%M"),
        })

    expenses_qs = Expense.objects.filter(tenant=tenant, date__gte=start_date, date__lte=end_date)
    expense_list_data = []
    expense_category = {}
    total_expense = 0
    for expense in expenses_qs:
        amount = float(expense.amount)
        total_expense += amount
        category = expense.category
        expense_category[category] = expense_category.get(category, 0) + amount
        expense_list_data.append({"category": category, "amount": amount, "date": expense.date.strftime("%d-%m-%Y"), "description": expense.description})

    total_income = total_membership_income + total_sales
    net_profit = total_income - total_expense

    return JsonResponse({
        "success": True, "period": period,
        "start_date": start_date.strftime("%Y-%m-%d"), "end_date": end_date.strftime("%Y-%m-%d"),
        "kpis": {
            "membership_income": total_membership_income, "product_sales": total_sales,
            "total_income": total_income, "total_expense": total_expense, "net_profit": net_profit,
        },
        "sales_category": sales_category, "expense_category": expense_category,
        "income_members": income_members, "sales": sales_list_data, "expenses": expense_list_data,
    })


# ============================================================
# AI: DIET + WORKOUT  (scoped via the member the plan is generated for)
# ============================================================

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_diet(request):
    tenant = get_tenant(request)

    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse(
            {"success": False, "error": "Please select a tenant first."},
            status=400
        )

    if tenant is None:
        return JsonResponse(
            {"success": False, "error": "User is not assigned to a tenant."},
            status=403
        )

    member_id = request.data.get("member_id")

    if not member_id:
        return JsonResponse(
            {"success": False, "error": "member_id is required."},
            status=400
        )

    member = get_object_or_404(
        Member,
        id=member_id,
        tenant=tenant,
        **get_branch_filter(request, tenant)
    )

    # Existing AI logic continues...

    age, gender, height, weight = member.age, member.gender, member.height, member.weight
    goal, food_category = member.goal, member.food_category

    client = Groq(api_key=settings.GROQ_API_KEY)

    prompt = f"""
You are an expert sports nutritionist.

Create a one-day personalized diet plan.

Member Details

Age: {age}
Gender: {gender}
Height: {height} cm
Weight: {weight} kg
Goal: {goal}
Food Category: {food_category}

Return ONLY valid JSON.

Do NOT include markdown.
Do NOT include ```json.
Do NOT include explanations.

Return exactly in this format:

{{
  "member": {{
    "age": {age},
    "gender": "{gender}",
    "height": {height},
    "weight": {weight},
    "goal": "{goal}",
    "food_category": "{food_category}"
  }},
  "nutrition": {{
    "daily_calories": "",
    "protein": "",
    "carbohydrates": "",
    "fat": "",
    "water": ""
  }},
  "meals": [
    {{"meal": "Breakfast", "time": "", "foods": [], "calories": ""}},
    {{"meal": "Morning Snack", "time": "", "foods": [], "calories": ""}},
    {{"meal": "Lunch", "time": "", "foods": [], "calories": ""}},
    {{"meal": "Evening Snack", "time": "", "foods": [], "calories": ""}},
    {{"meal": "Dinner", "time": "", "foods": [], "calories": ""}},
    {{"meal": "Before Bed", "time": "", "foods": [], "calories": ""}}
  ],
  "supplements": [],
  "foods_to_avoid": [],
  "shopping_list": [],
  "tips": []
}}
"""

    chat = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": "You are a certified sports nutritionist."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
    )

    ai_response = chat.choices[0].message.content

    try:
        diet_json = json.loads(ai_response)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "AI returned invalid JSON.", "raw_response": ai_response}, status=500)

    return JsonResponse({"success": True, "diet_plan": diet_json})

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_workout(request):
    tenant = get_tenant(request)
    member_id = request.data.get("member_id")

    # SUPER_ADMIN must select a tenant
    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return Response(
            {
                "success": False,
                "error": "Please select a tenant before generating workout."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    # Other users must belong to a tenant
    if tenant is None:
        return Response(
            {
                "success": False,
                "error": "User is not assigned to a tenant."
            },
            status=status.HTTP_403_FORBIDDEN
        )

    if not member_id:
        return Response(
            {
                "success": False,
                "error": "member_id is required"
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    # ---------------------------------------------------------
    # Get member within selected tenant + branch scope
    # ---------------------------------------------------------
    member = get_object_or_404(
        Member,
        id=member_id,
        tenant=tenant,
        **get_branch_filter(request, tenant)
    )

    # ---------------------------------------------------------
    # Get available gym equipment
    # ---------------------------------------------------------
    equipment = GymEquipment.objects.filter(
        tenant=tenant,
        is_available=True
    ).values_list("name", flat=True)

    equipment_list = list(equipment)

    # ---------------------------------------------------------
    # Groq client
    # ---------------------------------------------------------
    client = Groq(api_key=settings.GROQ_API_KEY)

    # ---------------------------------------------------------
    # AI Prompt
    # Existing workout generation logic preserved
    # ---------------------------------------------------------
    prompt = f"""
Create a personalized 6-day gym workout plan.

MEMBER:
Age: {member.age}
Gender: {member.gender}
Height: {member.height}
Weight: {member.weight}
Goal: {member.goal}

AVAILABLE GYM EQUIPMENT:
{equipment_list}

RULES:

- Use only the available equipment listed above.
- Bodyweight exercises are allowed.
- Create exactly 6 days.
- Each day should focus on a suitable body part.
- Do not train the same major body part on consecutive days.
- Make the workout suitable for the member's goal.
- Do not include images.
- Do not include explanations.
- Do not include unnecessary information.

For every workout provide:

- workout_name
- sets
- reps
- duration

Return ONLY valid JSON using exactly this structure:

{{
    "workout_plan": [
        {{
            "day": 1,
            "body_part": "Chest",
            "workouts": [
                {{
                    "workout_name": "Bench Press",
                    "sets": 3,
                    "reps": "10-12",
                    "duration": 10
                }}
            ]
        }}
    ]
}}
"""

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.4,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content

        workout_data = json.loads(content)

        return Response(
            {
                "success": True,
                "workout_plan": workout_data["workout_plan"]
            }
        )

    except json.JSONDecodeError:
        return Response(
            {
                "success": False,
                "error": "AI returned invalid JSON"
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    except Exception as e:
        return Response(
            {
                "success": False,
                "error": str(e)
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    

# ============================================================
# GYM EQUIPMENT
# ============================================================
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def gym_equipment(request):
    tenant = get_tenant(request)

    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return Response(
            {"success": False, "error": "Please select a tenant first."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if tenant is None:
        return Response(
            {"success": False, "error": "User is not assigned to a tenant."},
            status=status.HTTP_403_FORBIDDEN
        )

    if request.method == "GET":
        equipment = GymEquipment.objects.filter(
            tenant=tenant
        ).order_by("name")

        serializer = GymEquipmentSerializer(equipment, many=True)

        return Response({
            "success": True,
            "equipment": serializer.data
        })

    # POST
    if request.user.role not in ["SUPER_ADMIN", "TENANT_ADMIN"]:
        return Response(
            {
                "success": False,
                "error": "Only Super Admin and Tenant Admin can add equipment."
            },
            status=status.HTTP_403_FORBIDDEN
        )

    serializer = GymEquipmentSerializer(data=request.data)

    if serializer.is_valid():
        equipment = serializer.save(tenant=tenant)

        return Response({
            "success": True,
            "message": "Equipment added successfully",
            "equipment": GymEquipmentSerializer(equipment).data,
        }, status=status.HTTP_201_CREATED)

    return Response(
        {
            "success": False,
            "errors": serializer.errors
        },
        status=status.HTTP_400_BAD_REQUEST
    )


@api_view(["PUT", "DELETE"])
@permission_classes([IsAuthenticated])
def gym_equipment_detail(request, equipment_id):
    tenant = get_tenant(request)

    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return Response(
            {
                "success": False,
                "error": "Please select a tenant first."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    if tenant is None:
        return Response(
            {
                "success": False,
                "error": "User is not assigned to a tenant."
            },
            status=status.HTTP_403_FORBIDDEN
        )

    if request.user.role not in ["SUPER_ADMIN", "TENANT_ADMIN"]:
        return Response(
            {
                "success": False,
                "error": "You do not have permission to modify equipment."
            },
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        equipment = GymEquipment.objects.get(
            id=equipment_id,
            tenant=tenant
        )
    except GymEquipment.DoesNotExist:
        return Response(
            {
                "success": False,
                "error": "Equipment not found."
            },
            status=status.HTTP_404_NOT_FOUND
        )

    if request.method == "PUT":
        serializer = GymEquipmentSerializer(
            equipment,
            data=request.data
        )

        if serializer.is_valid():
            equipment = serializer.save()

            return Response({
                "success": True,
                "message": "Equipment updated successfully",
                "equipment": GymEquipmentSerializer(equipment).data
            })

        return Response(
            {
                "success": False,
                "errors": serializer.errors
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    if request.method == "DELETE":
        equipment.delete()

        return Response({
            "success": True,
            "message": "Equipment deleted successfully"
        })
    


from django.http import JsonResponse
import json
from datetime import datetime, date, timedelta

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated, BasePermission
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.shortcuts import get_object_or_404
from django.db.models import Sum

import csv
import io
import uuid

from .models import (
    Branch, Enquiry, Expense, GymEquipment, Payment, Product,
    Sales_product, Member, Income, MemberPause, Staffs, Plan,
)
from .serializers import GymEquipmentSerializer
from .tenant_utils import get_tenant, get_branch_filter


# ============================================================
# IMPORT CSV  (tenant-stamped on every created row)
# ============================================================

IMPORT_CONFIG = {
    "member": {
        "model": Member,
        "mapping": {
            "first_name": "name",
            "phone": "phone",
            "email": "email",
            "plan": "plan",
            "age": "age",
        },
    },
    "staff": {
        "model": Staffs,
        "mapping": {
            "first_name": "name",
            "number": "phone",
            "salary": "salary",
            "joindate": "joining_date",
        },
    },
}


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def import_csv(request):
    tenant = get_tenant(request)

    csv_file = request.FILES.get("file")
    model_type = request.data.get("model")

    if not csv_file:
        return Response({"success": False, "error": "CSV file is required."}, status=status.HTTP_400_BAD_REQUEST)

    if not model_type:
        return Response({"success": False, "error": "model is required."}, status=status.HTTP_400_BAD_REQUEST)

    config = IMPORT_CONFIG.get(model_type)
    if not config:
        return Response({"success": False, "error": f"Unsupported model: {model_type}"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        decoded_file = csv_file.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(decoded_file))

        Model = config["model"]
        mapping = config["mapping"]

        imported = []
        skipped = []

        for row_number, row in enumerate(reader, start=2):
            try:
                data = {"tenant": tenant}  # <-- stamp tenant on every imported row

                for csv_field, model_field in mapping.items():
                    value = row.get(csv_field, "")
                    if value is not None:
                        value = value.strip()
                    if value != "":
                        data[model_field] = value

                if model_type == "member":
                    data["id"] = str(uuid.uuid4())
                    if "age" in data:
                        data["age"] = int(data["age"])

                if model_type == "staff":
                    if "salary" in data:
                        data["salary"] = float(data["salary"])

                obj = Model.objects.create(**data)
                imported.append({"row": row_number, "id": obj.id})

            except Exception as e:
                skipped.append({"row": row_number, "error": str(e)})

        return Response({
            "success": True,
            "model": model_type,
            "imported_count": len(imported),
            "skipped_count": len(skipped),
            "imported": imported,
            "skipped": skipped,
        })

    except Exception as e:
        return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)




from django.http import JsonResponse
from datetime import datetime, date, timedelta

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from .models import Member, Plan, Branch, MemberPause
from .tenant_utils import get_tenant, get_branch_filter

# ============================================================
# PLANS
# ============================================================

from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db.models import Sum
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from .models import Member, Income, Expense, Sales_product, Payment, Plan
from .tenant_utils import get_tenant, get_branch_filter


def calculate_growth(current, previous):
    if previous == 0:
        return 100 if current > 0 else 0
    return round(((current - previous) / previous) * 100, 2)


import json
from datetime import date, datetime, timedelta

from django.conf import settings
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from groq import Groq

from .models import (
    Member, Staffs, Payment, Expense, Income, Product, Sales_product,
    Enquiry, GymEquipment, MemberPause,
)
from .serializers import GymEquipmentSerializer
from .tenant_utils import get_tenant, get_branch_filter
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def sell_product(request):
    tenant = get_tenant(request)

    # SUPER_ADMIN must select a tenant
    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse(
            {
                "success": False,
                "message": "Please select a tenant before selling a product."
            },
            status=400
        )

    # Other users must belong to a tenant
    if tenant is None:
        return JsonResponse(
            {
                "success": False,
                "message": "User is not assigned to a tenant."
            },
            status=403
        )

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {
                "success": False,
                "message": "Invalid JSON"
            },
            status=400
        )

    product_id = data.get("product_id")
    member_id = data.get("member_id")

    try:
        quantity = int(data.get("quantity", 0))
    except (ValueError, TypeError):
        return JsonResponse(
            {
                "success": False,
                "message": "Invalid quantity"
            },
            status=400
        )

    payment_method = data.get("payment_method", "cash")

    # ---------------------------------------------------------
    # Validate required data
    # ---------------------------------------------------------
    if not product_id or not member_id:
        return JsonResponse(
            {
                "success": False,
                "message": "Missing data"
            },
            status=400
        )

    if quantity <= 0:
        return JsonResponse(
            {
                "success": False,
                "message": "Invalid quantity"
            },
            status=400
        )

    # ---------------------------------------------------------
    # Get member within tenant + branch scope
    # ---------------------------------------------------------
    try:
        member = Member.objects.get(
            id=member_id,
            tenant=tenant,
            **get_branch_filter(request, tenant)
        )

    except Member.DoesNotExist:
        return JsonResponse(
            {
                "success": False,
                "message": "Member not found or access denied"
            },
            status=404
        )

    # ---------------------------------------------------------
    # Get product within selected tenant
    # ---------------------------------------------------------
    try:
        product = Product.objects.get(
            id=product_id,
            tenant=tenant
        )

    except Product.DoesNotExist:
        return JsonResponse(
            {
                "success": False,
                "message": "Product not found"
            },
            status=404
        )

    # ---------------------------------------------------------
    # Check stock
    # ---------------------------------------------------------
    if quantity > product.stock:
        return JsonResponse(
            {
                "success": False,
                "message": "Insufficient stock"
            },
            status=400
        )

    # ---------------------------------------------------------
    # Calculate sale amount
    # ---------------------------------------------------------
    unit_price = product.price
    total_amount = unit_price * quantity

    # ---------------------------------------------------------
    # Create sale
    # ---------------------------------------------------------
    sale = Sales_product.objects.create(
        tenant=tenant,
        member=member,
        product=product,
        quantity=quantity,
        unit_price=unit_price,
        total_amount=total_amount,
        payment_method=payment_method,
    )

    # ---------------------------------------------------------
    # Reduce product stock
    # ---------------------------------------------------------
    product.stock -= quantity
    product.save()

    return JsonResponse(
        {
            "success": True,
            "message": "Sale completed",
            "sale_id": sale.id
        },
        status=201
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def validate_member(request, member_id):
    tenant = get_tenant(request)

    # SUPER_ADMIN must select a tenant
    if request.user.role == "SUPER_ADMIN" and tenant is None:
        return JsonResponse(
            {
                "exists": False,
                "error": "Please select a tenant before validating a member."
            },
            status=400
        )

    # Other users must belong to a tenant
    if tenant is None:
        return JsonResponse(
            {
                "exists": False,
                "error": "User is not assigned to a tenant."
            },
            status=403
        )

    try:
        member = Member.objects.get(
            id=member_id,
            tenant=tenant,
            **get_branch_filter(request, tenant)
        )

        return JsonResponse({
            "exists": True,
            "member_name": member.name
        })

    except Member.DoesNotExist:
        return JsonResponse(
            {
                "exists": False,
                "message": "Member not found or access denied"
            },
            status=404
        )
    


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def expenses(request):
    tenant = get_tenant(request)
    qs = Expense.objects.filter(tenant=tenant).order_by("-date", "-id")

    data = [
        {
            "id": e.id, "title": e.title, "name": e.name, "phone": e.phone, "category": e.category,
            "description": e.description, "amount": str(e.amount), "payment_method": e.payment_method,
            "date": e.date.strftime("%Y-%m-%d"), "type": "Salary" if e.is_system_generated else "Additional",
        }
        for e in qs
    ]
    return JsonResponse(data, safe=False)