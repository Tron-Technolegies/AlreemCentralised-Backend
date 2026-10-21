from django.http import JsonResponse
import json
from datetime import datetime, date, timedelta

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated, BasePermission
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.shortcuts import get_object_or_404
from django.db.models import Sum
from django.contrib.auth import get_user_model

User = get_user_model()

from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from functools import wraps

import json
from datetime import datetime, timedelta

from django.http import JsonResponse
from rest_framework.permissions import IsAuthenticated

from .models import Member, MemberPause

# Membership pause policy


from django.utils import timezone

PAUSE_POLICIES = {
    30:  {"max_days": 0,  "max_requests": 0},
    60:  {"max_days": 7,  "max_requests": 1},
    90:  {"max_days": 15, "max_requests": 2},
    180: {"max_days": 30, "max_requests": 3},
    365: {"max_days": 45, "max_requests": 4},
}


def get_pause_policy(member):
    if not member.plan:
        return {"max_days": 0, "max_requests": 0}

    return PAUSE_POLICIES.get(
        member.plan.duration,
        {"max_days": 0, "max_requests": 0}
    )


def get_membership_pause_usage(member):
    """Return pause records and usage for the current membership cycle."""
    if not member.membership_start_date:
        return MemberPause.objects.none(), 0, 0

    pauses = MemberPause.objects.filter(
        tenant=member.tenant,
        member=member,
        start_date__gte=member.membership_start_date,
    )

    request_count = pauses.count()

    used_days = sum(
        pause.paused_days
        for pause in pauses
        if pause.end_date is not None
    )

    return pauses, request_count, used_days

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

            # Every application role must belong to a tenant
            if request.user.tenant_id is None:
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

    # TENANT_ADMIN can access everything inside their tenant
    if user.role == "TENANT_ADMIN":
        return {
            "tenant": user.tenant,
            "branch": None,
            "all_access": False,
        }

    # BRANCH_ADMIN and STAFF are restricted to their assigned branch
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
# LOGIN —
# ============================================================
@api_view(["POST"])
@permission_classes([AllowAny])
def admin_login(request):
    username = request.data.get("username")
    password = request.data.get("password")

    if not username or not password:
        return JsonResponse(
            {"error": "Username and password are required"},
            status=404
        )

    user = authenticate(username=username, password=password)

    if user is None:
        return JsonResponse(
            {"error": "Invalid username or password"},
            status=401
        )

    # Every application role must belong to a tenant
    if not getattr(user, "tenant_id", None):
        return JsonResponse(
            {"error": "This account is not linked to any gym."},
            status=403
        )

    refresh = RefreshToken.for_user(user)

    # Embed tenant context in the JWT itself
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
                "tenant_name": (
                    user.tenant.name
                    if getattr(user, "tenant", None)
                    else None
                ),
                "branch_id": getattr(user, "branch_id", None),
                "branch_name": (
                    user.branch.name
                    if getattr(user, "branch", None)
                    else None
                ),
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


from .models import Member, Plan, Branch, MemberPause
from .tenant_utils import get_tenant, get_branch_filter


# ============================================================
# MEMBERS
# ============================================================

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_member(request):
    tenant = get_tenant(request)

    # Every application role must have a tenant
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

        # if not branch_id:
        #     return JsonResponse(
        #         {"error": "Branch is required"},
        #         status=400
        #     )


        # -------------------------------------------------
        # BRANCH VALIDATION
        # -------------------------------------------------
        if request.user.role == "TENANT_ADMIN":
            # Tenant Admin must select a branch.
            if not branch_id:
                return JsonResponse(
                    {"error": "Branch is required"},
                    status=400
                )

            branch = Branch.objects.filter(
                id=branch_id,
                tenant=tenant
            ).first()

            if not branch:
                return JsonResponse(
                    {"error": "Invalid branch selected"},
                    status=400
                )

        elif request.user.role in ["BRANCH_ADMIN", "STAFF"]:
            # Use the branch assigned to the logged-in user.
            if not request.user.branch_id:
                return JsonResponse(
                    {"error": "Your account is not assigned to a branch"},
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

        else:
            return JsonResponse(
                {"error": "Permission denied"},
                status=403
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
            branch=branch,
            phone=phone
        ).exists():
            return JsonResponse(
                {"error": "Mobile number already exists in this branch"},
                status=400
            )

        # -------------------------------------------------
        # Email validation
        # -------------------------------------------------

        if email and Member.objects.filter(
            tenant=tenant,
            branch=branch,
            email__iexact=email
        ).exists():
            return JsonResponse(
                {"error": "Email already exists in this branch"},
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
        # BRANCH VALIDATION
        # -------------------------------------------------
        # if request.user.role == "TENANT_ADMIN":
        #     # Only Tenant Admin selects a branch from the dropdown.
        #     if not branch_id:
        #         return JsonResponse(
        #             {"error": "Branch is required"},
        #             status=400
        #         )

        #     branch = Branch.objects.filter(
        #         id=branch_id,
        #         tenant=tenant
        #     ).first()

        #     if not branch:
        #         return JsonResponse(
        #             {"error": "Invalid branch selected"},
        #             status=400
        #         )

        # elif request.user.role in ["BRANCH_ADMIN", "STAFF"]:
        #     # Automatically use the user's assigned branch.
        #     if not request.user.branch_id:
        #         return JsonResponse(
        #             {
        #                 "error": (
        #                     "Your account is not assigned to a branch. "
        #                     "Please contact your administrator."
        #                 )
        #             },
        #             status=403
        #         )

        #     branch = Branch.objects.filter(
        #         id=request.user.branch_id,
        #         tenant=tenant
        #     ).first()

        #     if not branch:
        #         return JsonResponse(
        #             {"error": "Invalid branch assignment"},
        #             status=403
        #         )

        # else:
        #     return JsonResponse(
        #         {"error": "Permission denied"},
        #         status=403
        #     )

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
            tenant=tenant,

            id=next_id,

            name=request.POST.get("name"),

            phone=phone,

            email=email,

            plan=plan,

            branch=branch,
            join_date=join_date,
            membership_start_date=join_date,
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
    if not member.is_paused or not member.pause_expiry_date:
        return

    if today < member.pause_expiry_date:
        return

    pause = MemberPause.objects.filter(
        tenant=member.tenant,
        member=member,
        end_date__isnull=True,
    ).order_by("-start_date").first()

    if pause:
        # Use the approved end date, not today's date.
        actual_resume_date = member.pause_expiry_date

        paused_days = (
            actual_resume_date - pause.start_date
        ).days

        paused_days = max(
            0, min(paused_days, pause.allowed_days)
        )

        pause.end_date = actual_resume_date
        pause.paused_days = paused_days
        pause.save()

        if member.expiry_date:
            member.expiry_date += timedelta(days=paused_days)

    _, _, used_days = get_membership_pause_usage(member)

    member.is_paused = False
    member.pause_start_date = None
    member.pause_expiry_date = None
    member.used_pause_days = used_days
    member.status = "Active"
    member.save()


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_members(request):

    tenant = get_tenant(request)
    today = date.today()

    # -------------------------------------------------
    # Tenant validation
    # -------------------------------------------------

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

            "food_category": (
                member.get_food_category_display()
            ),

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

    return JsonResponse(data,safe=False)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_member(request, member_id):

    tenant = get_tenant(request)

    # -------------------------------------------------
    # Tenant validation
    # -------------------------------------------------

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

            today = timezone.localdate()

            if member.expiry_date < today:
                days_expired = (today -member.expiry_date).days
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
        # Membership pause policy and usage
        # -------------------------------------------------
        policy = get_pause_policy(member)

        _, pause_count, pause_days_used = (
            get_membership_pause_usage(member)
        )

        pause_days_remaining = max(
            0, policy["max_days"] - pause_days_used
        )

        remaining_pause_requests = max(
            0, policy["max_requests"] - pause_count
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

                "max_pause_days": policy["max_days"],
                "max_pause_requests": policy["max_requests"],
                "pause_days_used": pause_days_used,
                "pause_days_remaining": pause_days_remaining,
                "pause_count": pause_count,
                "remaining_pause_requests": remaining_pause_requests,
                "pause_start_date": (
                    member.pause_start_date.isoformat()
                    if member.pause_start_date
                    else None
                ),
                "membership_start_date": (
                member.membership_start_date.isoformat()
                if member.membership_start_date
                else None
            ),

                "used_pause_days": member.used_pause_days,
                "pause_expiry_date": (
                    member.pause_expiry_date.isoformat()
                    if member.pause_expiry_date
                    else None
                ),},status=200)

    except Member.DoesNotExist:
        return JsonResponse({"error": "Member not found"},status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)},status=500)
    
    
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def update_member(request, member_id):

    tenant = get_tenant(request)

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

        # -------------------------------------------------
        # Height / Weight / BMI
        # -------------------------------------------------

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

        # -------------------------------------------------
        # Paid amount
        # -------------------------------------------------

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

        # -------------------------------------------------
        # Plan amount
        # -------------------------------------------------

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

        # -------------------------------------------------
        # Expiry date
        # -------------------------------------------------

        expiry_date = member.expiry_date

        if join_date and selected_plan:

            duration = int(
                selected_plan.duration or 0
            )

            expiry_date = (
                join_date +
                timedelta(days=duration)
            )

        # -------------------------------------------------
        # Update member
        # -------------------------------------------------

        member.name = name

        member.phone = phone

        member.email = email

        member.plan = selected_plan

        member.height = height

        member.weight = weight

        member.bmi = bmi

        member.goal = goal

        member.food_category = food_category

        member.age = request.data.get(
            "age",
            member.age
        )

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

        # -------------------------------------------------
        # Photo
        # -------------------------------------------------

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

    if tenant is None:

        return JsonResponse(
            {
                "error":
                "User is not assigned to a tenant"
            },
            status=403
        )

    # -------------------------------------------------
    # STAFF cannot delete members
    # -------------------------------------------------

    if request.user.role == "STAFF":

        return JsonResponse(
            {
                "error":
                "Staff members are not allowed to delete members"
            },
            status=403
        )

    # -------------------------------------------------
    # Only TENANT_ADMIN and BRANCH_ADMIN can delete
    # -------------------------------------------------

    if request.user.role not in [
        "TENANT_ADMIN",
        "BRANCH_ADMIN"
    ]:

        return JsonResponse(
            {
                "error":
                "Permission denied"
            },
            status=403
        )

    try:

        member = Member.objects.get(
            id=member_id,
            tenant=tenant,
            **get_branch_filter(
                request,
                tenant
            )
        )

    except Member.DoesNotExist:

        return JsonResponse(
            {
                "error":
                "Member not found or access denied"
            },
            status=404
        )

    member.delete()

    return JsonResponse(
        {
            "message":
            "Member deleted successfully",

            "member_id":
            member_id
        },
        status=200
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_plan(request):
    tenant = get_tenant(request)

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    # Only Tenant Admin can create plans
    if request.user.role != "TENANT_ADMIN":
        return JsonResponse(
            {"error": "Only Tenant Admin can create plans"},
            status=403
        )

    Plan.objects.create(
        tenant=tenant,
        name=request.POST.get("name"),
        duration=request.POST.get("duration"),
        price=request.POST.get("price"),
    )

    return JsonResponse(
        {"message": "Plan created successfully"},
        status=201
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_plans(request):
    tenant = get_tenant(request)

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    # All roles can view plans belonging to their tenant
    plans = list(
        Plan.objects
        .filter(tenant=tenant)
        .order_by("id")
        .values()
    )

    return JsonResponse(
        plans,
        safe=False
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def update_plan(request, plan_id):
    tenant = get_tenant(request)

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    # Only Tenant Admin can update plans
    if request.user.role != "TENANT_ADMIN":
        return JsonResponse(
            {"error": "Only Tenant Admin can update plans"},
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

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    # Only Tenant Admin can delete plans
    if request.user.role != "TENANT_ADMIN":
        return JsonResponse(
            {"error": "Only Tenant Admin can delete plans"},
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


from datetime import date, datetime, timedelta
from django.db import transaction, IntegrityError
from django.http import JsonResponse


User = get_user_model()


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_branch(request):
    """Create a branch and its Branch Admin account atomically."""

    tenant = get_tenant(request)

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403,
        )

    if request.user.role != "TENANT_ADMIN":
        return JsonResponse(
            {"error": "Only Tenant Admin can create branches"},
            status=403,
        )

    data = request.data

    name = str(data.get("name", "")).strip()
    location = str(data.get("location", "")).strip()
    manager_name = str(data.get("manager_name", "")).strip()
    phone = str(data.get("phone", "")).strip()
    capacity_value = data.get("capacity")
    username = str(data.get("admin_username", "")).strip()
    password = data.get("admin_password", "")

    if not name:
        return JsonResponse({"error": "Branch name is required"}, status=400)

    if not phone.isdigit() or len(phone) != 10:
        return JsonResponse(
            {"error": "Enter a valid 10-digit mobile number"},
            status=400,
        )

    try:
        capacity = int(capacity_value)
        if capacity <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return JsonResponse(
            {"error": "Capacity must be a positive whole number"},
            status=400,
        )

    if not username:
        return JsonResponse(
            {"error": "Branch admin username is required"},
            status=400,
        )

    if not isinstance(password, str) or len(password) < 8:
        return JsonResponse(
            {"error": "Branch admin password must be at least 8 characters"},
            status=400,
        )

    if User.objects.filter(username__iexact=username).exists():
        return JsonResponse(
            {"error": "This username is already taken"},
            status=400,
        )

    try:
        with transaction.atomic():
            branch = Branch.objects.create(
                tenant=tenant,
                name=name,
                location=location,
                manager_name=manager_name,
                phone=phone,
                capacity=capacity,
            )

            admin_user = User.objects.create_user(
                username=username,
                password=password,
                role="BRANCH_ADMIN",
                tenant=tenant,
                branch=branch,
            )

    except IntegrityError:
        return JsonResponse(
            {
                "error": (
                    "Unable to create the branch or admin account. "
                    "Check for duplicate values and try again."
                )
            },
            status=400,
        )

    return JsonResponse(
        {
            "message": "Branch and Branch Admin account created successfully",
            "branch": {
                "id": branch.id,
                "name": branch.name,
                "location": branch.location,
                "manager_name": branch.manager_name,
                "phone": branch.phone,
                "capacity": branch.capacity,
            },
            "admin": {
                "id": admin_user.id,
                "username": admin_user.username,
                "role": admin_user.role,
            },
        },
        status=201,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_branches(request):
    """List branches belonging to the logged-in user's tenant."""

    tenant = get_tenant(request)

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403,
        )

    branches = Branch.objects.filter(tenant=tenant)

    if request.user.role in ["BRANCH_ADMIN", "STAFF"]:
        if request.user.branch_id is None:
            return JsonResponse(
                {"error": "Your account is not assigned to a branch"},
                status=403,
            )

        branches = branches.filter(id=request.user.branch_id)

    elif request.user.role != "TENANT_ADMIN":
        return JsonResponse({"error": "Permission denied"}, status=403)

    branch_data = list(
        branches.order_by("id").values(
            "id",
            "name",
            "location",
            "manager_name",
            "phone",
            "capacity",
            "tenant_id",
        )
    )

    return JsonResponse(branch_data, safe=False, status=200)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_branch_members(request, branch_id):
    """List members belonging to a specific branch."""

    tenant = get_tenant(request)

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403,
        )

    if request.user.role not in ["TENANT_ADMIN", "BRANCH_ADMIN", "STAFF"]:
        return JsonResponse({"error": "Permission denied"}, status=403)

    try:
        branch = Branch.objects.get(
            id=branch_id,
            tenant=tenant,
        )
    except Branch.DoesNotExist:
        return JsonResponse({"error": "Branch not found"}, status=404)

    if request.user.role in ["BRANCH_ADMIN", "STAFF"]:
        if request.user.branch_id != branch.id:
            return JsonResponse(
                {"error": "You cannot access another branch"},
                status=403,
            )

    members = Member.objects.filter(
        tenant=tenant,
        branch=branch,
    ).order_by("id")

    # Return model fields without exposing unrelated tenant data.
    member_data = list(
        members.values(
            "id",
            "branch_id",
            "tenant_id",
        )
    )

    return JsonResponse(
        {
            "branch": {
                "id": branch.id,
                "name": branch.name,
            },
            "count": len(member_data),
            "members": member_data,
        },
        status=200,
    )


@api_view(["PUT", "PATCH"])
@permission_classes([IsAuthenticated])
def update_branch(request, branch_id):
    """Update a branch within the logged-in user's tenant."""

    tenant = get_tenant(request)

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403,
        )

    if request.user.role not in ["TENANT_ADMIN", "BRANCH_ADMIN"]:
        return JsonResponse(
            {"error": "You do not have permission to update branches"},
            status=403,
        )

    try:
        branch = Branch.objects.get(
            id=branch_id,
            tenant=tenant,
        )
    except Branch.DoesNotExist:
        return JsonResponse({"error": "Branch not found"}, status=404)

    if request.user.role == "BRANCH_ADMIN":
        if request.user.branch_id != branch.id:
            return JsonResponse(
                {"error": "You cannot update another branch"},
                status=403,
            )

    data = request.data

    if "name" in data:
        name = str(data.get("name", "")).strip()
        if not name:
            return JsonResponse(
                {"error": "Branch name cannot be empty"},
                status=400,
            )
        branch.name = name

    if "location" in data:
        branch.location = str(data.get("location", "")).strip()

    if "manager_name" in data:
        branch.manager_name = str(data.get("manager_name", "")).strip()

    if "phone" in data:
        phone = str(data.get("phone", "")).strip()
        if not phone.isdigit() or len(phone) != 10:
            return JsonResponse(
                {"error": "Enter a valid 10-digit mobile number"},
                status=400,
            )
        branch.phone = phone

    if "capacity" in data:
        try:
            capacity = int(data.get("capacity"))
            if capacity <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return JsonResponse(
                {"error": "Capacity must be a positive whole number"},
                status=400,
            )
        branch.capacity = capacity

    branch.save()

    return JsonResponse(
        {
            "message": "Branch updated successfully",
            "branch": {
                "id": branch.id,
                "name": branch.name,
                "location": branch.location,
                "manager_name": branch.manager_name,
                "phone": branch.phone,
                "capacity": branch.capacity,
            },
        },
        status=200,
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_branch(request, branch_id):
    """Delete a branch, only if it has no members."""

    tenant = get_tenant(request)

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403,
        )

    if request.user.role != "TENANT_ADMIN":
        return JsonResponse(
            {"error": "Only Tenant Admin can delete branches"},
            status=403,
        )

    try:
        branch = Branch.objects.get(
            id=branch_id,
            tenant=tenant,
        )
    except Branch.DoesNotExist:
        return JsonResponse({"error": "Branch not found"}, status=404)

    if Member.objects.filter(
        tenant=tenant,
        branch=branch,
    ).exists():
        return JsonResponse(
            {
                "error": (
                    "This branch has members. Transfer or remove its members "
                    "before deleting the branch."
                )
            },
            status=400,
        )

    branch_name = branch.name
    branch.delete()

    return JsonResponse(
        {
            "message": f"Branch '{branch_name}' deleted successfully",
        },
        status=200,
    )


from decimal import Decimal

from django.db.models import Sum
from django.http import JsonResponse


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

    # All users must belong to a tenant
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
    # INCOME:
    #   - Member / Membership fees
    #   - Product sales
    #
    # EXPENSE:
    #   - Salary
    #   - Other expenses
    #
    # Tenant scoped
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
    # BRANCH FINANCIAL FILTER
    # Branch Admin + Staff → Own Branch Only
    # =====================================================

    if request.user.role in [
        "BRANCH_ADMIN",
        "STAFF"
    ]:

        if not request.user.branch_id:

            return JsonResponse(
                {
                    "error":
                        "User is not assigned to a branch"
                },
                status=403
            )

        income_qs = income_qs.filter(
            branch_id=request.user.branch_id
        )

        sales_qs = sales_qs.filter(
            branch_id=request.user.branch_id
        )

        expense_qs = expense_qs.filter(
            branch_id=request.user.branch_id
        )

    # =====================================================
    # TOTAL / ALL-TIME INCOME
    # =====================================================

    # Member / Membership fees
    total_membership_income = (
        income_qs
        .aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0")
    )

    # Product sales
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
    #
    # Salary + Other Expenses
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
    #
    # Member fees -> Income
    # Product sales -> Income
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

        "total_income": f"{period_income:.2f}",
        "total_sales": f"{period_sales:.2f}",
        "total_expense": f"{period_expense:.2f}",
        "total_profit": f"{period_profit:.2f}",
        "period_loss": f"{period_loss:.2f}",

        "today_income": f"{today_income:.2f}",
        "today_sales": f"{today_sales:.2f}",
        "today_expense": f"{today_expense:.2f}",
        "today_profit": f"{today_profit:.2f}",
        "today_loss": f"{today_loss:.2f}",

        "monthly_income": f"{monthly_income:.2f}",
        "monthly_sales": f"{monthly_sales:.2f}",
        "monthly_expense": f"{monthly_expense:.2f}",
        "monthly_profit": f"{monthly_profit:.2f}",
        "monthly_loss": f"{monthly_loss:.2f}",

        "yearly_income": f"{yearly_income:.2f}",
        "yearly_sales": f"{yearly_sales:.2f}",
        "yearly_expense": f"{yearly_expense:.2f}",
        "yearly_profit": f"{yearly_profit:.2f}",
        "yearly_loss": f"{yearly_loss:.2f}",

        "all_time_income": f"{total_income:.2f}",
        "all_time_sales": f"{total_product_income:.2f}",
        "all_time_expense": f"{total_expense:.2f}",
        "all_time_profit": f"{total_profit:.2f}",
        "total_loss": f"{total_loss:.2f}",

        "membership_income": f"{membership_income:.2f}",
        "product_income": f"{product_income:.2f}",
        "admission_income": f"{admission_income:.2f}",

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

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_blocked_members(request):

    tenant = get_tenant(request)

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

    if tenant is None:
        return JsonResponse(
            {
                "error":
                    "User is not assigned to a tenant"
            },
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
            {
                "error":
                    "Member not found or access denied"
            },
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

    if tenant is None:
        return JsonResponse(
            {
                "error":
                    "User is not assigned to a tenant"
            },
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

    if tenant is None:
        return JsonResponse(
            {
                "error":
                    "User is not assigned to a tenant"
            },
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


from groq import Groq

# ===================================
# PRODUCTS 
# ===================================

from .tenant_utils import get_tenant, get_branch_filter

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_product(request):

    tenant = get_tenant(request)

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    if request.user.role not in [
        "TENANT_ADMIN",
        "BRANCH_ADMIN"
    ]:
        return JsonResponse(
            {"error": "You do not have permission to create products"},
            status=403
        )

    # Branch Admin can only create products for their own branch
    if request.user.role == "BRANCH_ADMIN":

        branch = request.user.branch

        if branch is None:
            return JsonResponse(
                {"error": "User is not assigned to a branch"},
                status=403
            )

        if branch.tenant != tenant:
            return JsonResponse(
                {"error": "Invalid branch"},
                status=403
            )

    else:
        # TENANT_ADMIN
        # Branch comes from request
        branch_id = request.POST.get("branch")

        if not branch_id:
            return JsonResponse(
                {"error": "Branch is required"},
                status=400
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

    product = Product.objects.create(
        tenant=tenant,
        branch=branch,
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

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    products = Product.objects.filter(
        tenant=tenant
    )

    if request.user.role in ["BRANCH_ADMIN", "STAFF"]:

        if request.user.branch is None:
            return JsonResponse(
                {"error": "User is not assigned to a branch"},
                status=403
            )

        products = products.filter(
            branch=request.user.branch
        )

    products = products.order_by("id")

    data = [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "price": p.price,
            "stock": p.stock,
            "category": p.category,
            "branch": p.branch.id,
            "branch_name": p.branch.name,
            "image": p.image.url if p.image else None,
        }
        for p in products
    ]

    return JsonResponse(data, safe=False)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def update_product(request, product_id):

    tenant = get_tenant(request)

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    if request.user.role not in [
        "TENANT_ADMIN",
        "BRANCH_ADMIN"
    ]:
        return JsonResponse(
            {"error": "You do not have permission to update products"},
            status=403
        )

    try:
        product = Product.objects.get(
            id=product_id,
            tenant=tenant
        )

        # Branch Admin can only update own branch product
        if request.user.role == "BRANCH_ADMIN":

            if request.user.branch is None:
                return JsonResponse(
                    {"error": "User is not assigned to a branch"},
                    status=403
                )

            if product.branch != request.user.branch:
                return JsonResponse(
                    {
                        "error":
                        "You can only update products in your branch"
                    },
                    status=403
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

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    if request.user.role not in [
        "TENANT_ADMIN",
        "BRANCH_ADMIN"
    ]:
        return JsonResponse(
            {"error": "You do not have permission to delete products"},
            status=403
        )

    try:
        product = Product.objects.get(
            id=product_id,
            tenant=tenant
        )

        # Branch Admin can only delete own branch product
        if request.user.role == "BRANCH_ADMIN":

            if request.user.branch is None:
                return JsonResponse(
                    {"error": "User is not assigned to a branch"},
                    status=403
                )

            if product.branch != request.user.branch:
                return JsonResponse(
                    {
                        "error":
                        "You can only delete products in your branch"
                    },
                    status=403
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

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    period = request.GET.get("period", "daily").lower()
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
            "product__branch",
            "member",
            "member__branch"
        )
    )

    # Branch filtering according to the user's role.
    role = request.user.role

    if role in ["BRANCH_ADMIN", "STAFF"]:
        if not request.user.branch_id:
            return JsonResponse(
                {"error": "User is not assigned to a branch"},
                status=403
            )

        sales = sales.filter(
            product__branch_id=request.user.branch_id
        )

    elif role == "TENANT_ADMIN":
        branch_id = request.GET.get("branch", "all")

        if branch_id != "all":
            try:
                branch = Branch.objects.get(
                    id=branch_id,
                    tenant=tenant
                )
            except (Branch.DoesNotExist, ValueError, TypeError):
                return JsonResponse(
                    {"error": "Invalid branch selected"},
                    status=400
                )

            sales = sales.filter(
                product__branch_id=branch.id
            )

    else:
        return JsonResponse(
            {"error": "You do not have permission to view sales"},
            status=403
        )

    sales = sales.order_by("-sold_at")

    data = []

    for sale in sales:
        product_branch = getattr(
            sale.product,
            "branch",
            None
        )

        data.append({
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
            "unit_price": float(sale.unit_price),
            "total_amount": float(sale.total_amount),

            "sold_at": sale.sold_at.strftime(
                "%d-%m-%Y %H:%M"
            ),

            "branch": (
                {
                    "id": product_branch.id,
                    "name": product_branch.name,
                }
                if product_branch
                else None
            ),
        })

    return JsonResponse({
        "success": True,
        "period": period,
        "start_date": start_date,
        "end_date": end_date,
        "sales": data,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def one_sale(request, sale_id):

    tenant = get_tenant(request)

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    try:
        sale = (
            Sales_product.objects
            .select_related(
                "product",
                "member",
                "member__branch"
            )
            .get(
                id=sale_id,
                tenant=tenant
            )
        )

    except Sales_product.DoesNotExist:
        return JsonResponse(
            {"error": "Sale not found"},
            status=404
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

        if not sale.member or sale.member.branch_id != request.user.branch_id:
            return JsonResponse(
                {"error": "You can only view sales from your branch"},
                status=403
            )

    return JsonResponse({
        "id": sale.id,

        "member_id": sale.member_id,

        "member_name": (
            sale.member.name
            if sale.member
            else None
        ),

        "product": (
            getattr(
                sale.product,
                "name",
                str(sale.product)
            )
        ),

        "quantity": sale.quantity,

        "unit_price": float(
            sale.unit_price
        ),

        "total_amount": float(
            sale.total_amount
        ),

        "payment_method": sale.payment_method,

        "sold_at": sale.sold_at,

        "invoice_no": getattr(
            sale,
            "invoice_no",
            f"INV-{sale.id}"
        ),
    })


# ============================================================
# STAFF
# ============================================================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_staff(request):

    # TENANT_ADMIN and BRANCH_ADMIN can create staff
    if request.user.role not in [
        "TENANT_ADMIN",
        "BRANCH_ADMIN"
    ]:
        return JsonResponse(
            {"error": "You do not have permission to create staff"},
            status=403
        )

    tenant = get_tenant(request)

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    # Branch Admin must have a branch
    if request.user.role == "BRANCH_ADMIN":

        if not request.user.branch_id:
            return JsonResponse(
                {"error": "You are not assigned to a branch"},
                status=403
            )

        # Branch Admin can only create staff in own branch
        branch = Branch.objects.filter(
            id=request.user.branch_id,
            tenant=tenant
        ).first()

        if not branch:
            return JsonResponse(
                {"error": "Invalid branch assignment"},
                status=403
            )

    else:
        # TENANT_ADMIN
        branch_id = request.POST.get("branch")

        if not branch_id:
            return JsonResponse(
                {"error": "Branch is required"},
                status=400
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

from django.db.models import Sum

from django.http import JsonResponse


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_staffs(request):

    tenant = get_tenant(request)

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    # ----------------------------------
    # GET STAFFS
    # ----------------------------------

    staffs = (
        Staffs.objects
        .filter(tenant=tenant)
        .select_related("branch")
        .order_by("-id")
    )

    # ----------------------------------
    # BRANCH RESTRICTION
    # ----------------------------------

    if request.user.role in ["BRANCH_ADMIN", "STAFF"]:

        if not request.user.branch_id:
            return JsonResponse(
                {"error": "User is not assigned to a branch"},
                status=403
            )

        staffs = staffs.filter(
            branch_id=request.user.branch_id
        )

    # ----------------------------------
    # RESPONSE DATA
    # ----------------------------------

    data = []

    for staff in staffs:

        paid_amount = (
            Payment.objects
            .filter(
                tenant=tenant,
                staff=staff
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

            # "salary": str(staff.salary),
            "salary": f"{staff.salary:.2f}",

            # ALL payment transactions
            # "paid_amount": str(paid_amount),
            "paid_amount": f"{paid_amount:.2f}",

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

    return JsonResponse(data,safe=False)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_staff(request, staff_id):

    tenant = get_tenant(request)

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    # ----------------------------------
    # GET STAFF
    # ----------------------------------

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

    # ----------------------------------
    # BRANCH RESTRICTION
    # ----------------------------------

    if request.user.role in ["BRANCH_ADMIN", "STAFF"]:

        if not request.user.branch_id:
            return JsonResponse(
                {"error": "User is not assigned to a branch"},
                status=403
            )

        if staff.branch_id != request.user.branch_id:
            return JsonResponse(
                {
                    "error": "You are not permitted to access this staff member"
                },
                status=403
            )

    # ----------------------------------
    # TOTAL PAID
    #
    # Includes ALL payment types
    # ----------------------------------

    paid_amount = (
        Payment.objects
        .filter(
            tenant=tenant,
            staff=staff
        )
        .aggregate(
            total=Sum("amount")
        )["total"]
        or 0
    )

    # ----------------------------------
    # RESPONSE
    # ----------------------------------

    return JsonResponse({

        "id": staff.id,
        "name": staff.name,
        "role": staff.role,
        "specialization": staff.specialization,
        "phone": staff.phone,
        "experience": staff.experience,
        "joining_date": staff.joining_date,

        # "salary": str(staff.salary),
        "salary": f"{staff.salary:.2f}",

        # ALL payment transactions
        # "paid_amount": str(paid_amount),
        "paid_amount": f"{paid_amount:.2f}",

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

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    if request.user.role not in [
        "TENANT_ADMIN",
        "BRANCH_ADMIN"
    ]:
        return JsonResponse(
            {"error": "You do not have permission to update staff"},
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

    # Branch Admin → own branch only
    if request.user.role == "BRANCH_ADMIN":

        if not request.user.branch_id:
            return JsonResponse(
                {"error": "You are not assigned to a branch"},
                status=403
            )

        if staff.branch_id != request.user.branch_id:
            return JsonResponse(
                {"error": "You can only update staff in your branch"},
                status=403
            )

        # Branch Admin cannot move staff to another branch
        branch = staff.branch

    else:
        # TENANT_ADMIN can change branch
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

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403
        )

    if request.user.role not in [
        "TENANT_ADMIN",
        "BRANCH_ADMIN"
    ]:
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

    # Branch Admin → own branch only
    if request.user.role == "BRANCH_ADMIN":

        if not request.user.branch_id:
            return JsonResponse(
                {"error": "You are not assigned to a branch"},
                status=403
            )

        if staff.branch_id != request.user.branch_id:
            return JsonResponse(
                {
                    "error":
                    "You can only delete staff in your branch"
                },
                status=403
            )

    staff.delete()

    return JsonResponse(
        {"message": "Staff deleted successfully"},
        status=200
    )


# ============================================================
# PAUSE / RESUME
# ============================================================

import json
from datetime import datetime, timedelta

from django.http import JsonResponse

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def pause_member(request, member_id):
    tenant = get_tenant(request)

    if tenant is None:
        return JsonResponse({
            "success": False,
            "error": "User is not assigned to a tenant."
        }, status=403)

    if request.user.role == "STAFF":
        return JsonResponse({
            "success": False,
            "error": "Staff members are not allowed to pause members."
        }, status=403)

    try:
        freeze_date = datetime.strptime(
            str(request.data.get("freeze_date", "")),
            "%Y-%m-%d"
        ).date()
    except (ValueError, TypeError):
        return JsonResponse({
            "success": False,
            "error": "Valid freeze_date is required (YYYY-MM-DD)."
        }, status=400)

    today = timezone.localdate()

    if freeze_date > today:
        return JsonResponse({
            "success": False,
            "error": "Future pause dates are not allowed."
        }, status=400)

    with transaction.atomic():
        try:
            member = Member.objects.select_for_update().get(
                id=member_id,
                tenant=tenant,
                **get_branch_filter(request, tenant)
            )
        except Member.DoesNotExist:
            return JsonResponse({
                "success": False,
                "error": "Member not found or access denied."
            }, status=404)

        if member.is_paused:
            return JsonResponse({
                "success": False,
                "error": "Member is already paused."
            }, status=400)

        if not member.plan or not member.membership_start_date:
            return JsonResponse({
                "success": False,
                "error": (
                    "A membership plan and membership start date "
                    "are required."
                )
            }, status=400)

        if member.plan.tenant_id != tenant.id:
            return JsonResponse({
                "success": False,
                "error": "Member plan does not belong to this tenant."
            }, status=400)

        if freeze_date < member.membership_start_date:
            return JsonResponse({
                "success": False,
                "error": (
                    "Pause date cannot be before the current "
                    "membership start date."
                )
            }, status=400)

        if member.expiry_date and freeze_date >= member.expiry_date:
            return JsonResponse({
                "success": False,
                "error": "Cannot pause a membership on or after its expiry date."
            }, status=400)

        if member.expiry_date and member.expiry_date < today:
            return JsonResponse({
                "success": False,
                "error": "Cannot pause an expired membership."
            }, status=400)

        policy = get_pause_policy(member)
        max_days = policy["max_days"]
        max_requests = policy["max_requests"]

        if max_days <= 0 or max_requests <= 0:
            return JsonResponse({
                "success": False,
                "error": "Pause is not available for this membership plan.",
                "max_pause_days": max_days,
                "max_pause_requests": max_requests
            }, status=400)

        active_pause_exists = MemberPause.objects.filter(
            tenant=tenant,
            member=member,
            end_date__isnull=True
        ).exists()

        if active_pause_exists:
            return JsonResponse({
                "success": False,
                "error": "An active pause record already exists."
            }, status=400)

        _, request_count, used_days = get_membership_pause_usage(member)

        if request_count >= max_requests:
            return JsonResponse({
                "success": False,
                "error": "Maximum pause requests for this membership have been used.",
                "used_requests": request_count,
                "max_pause_requests": max_requests
            }, status=400)

        remaining_days = max(0, max_days - used_days)

        if remaining_days <= 0:
            return JsonResponse({
                "success": False,
                "error": "Maximum pause days for this membership have been used.",
                "used_days": used_days,
                "remaining_days": 0,
                "max_pause_days": max_days
            }, status=400)

        allowed_days = remaining_days
        allowed_resume_date = freeze_date + timedelta(days=allowed_days)

        pause = MemberPause.objects.create(
            tenant=tenant,
            member=member,
            start_date=freeze_date,
            allowed_days=allowed_days,
            paused_days=0
        )

        member.is_paused = True
        member.pause_start_date = freeze_date
        member.pause_expiry_date = allowed_resume_date
        member.used_pause_days = used_days
        member.status = "Paused"

        member.save(update_fields=[
            "is_paused",
            "pause_start_date",
            "pause_expiry_date",
            "used_pause_days",
            "status"
        ])

    return JsonResponse({
        "success": True,
        "message": "Member paused successfully.",
        "pause_id": pause.id,
        "pause_start_date": freeze_date.isoformat(),
        "pause_days_used": used_days,
        "pause_days_remaining": remaining_days,
        "pause_count": request_count + 1,
        "remaining_pause_requests": max(
            0, max_requests - request_count - 1
        ),
        "allowed_days": allowed_days,
        "allowed_resume_date": allowed_resume_date.isoformat(),
        "max_pause_days": max_days,
        "max_pause_requests": max_requests,
        "status": member.status,
        "is_paused": member.is_paused
    })

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def resume_member(request, member_id):
    tenant = get_tenant(request)

    if tenant is None:
        return JsonResponse({
            "success": False,
            "error": "User is not assigned to a tenant."
        }, status=403)

    if request.user.role == "STAFF":
        return JsonResponse({
            "success": False,
            "error": "Staff members are not allowed to resume members."
        }, status=403)

    try:
        resume_date = datetime.strptime(
            str(request.data.get("resume_date", "")),
            "%Y-%m-%d"
        ).date()
    except (ValueError, TypeError):
        return JsonResponse({
            "success": False,
            "error": "Valid resume_date is required (YYYY-MM-DD)."
        }, status=400)

    today = timezone.localdate()

    if resume_date > today:
        return JsonResponse({
            "success": False,
            "error": "Future resume dates are not allowed."
        }, status=400)

    with transaction.atomic():
        try:
            member = Member.objects.select_for_update().get(
                id=member_id,
                tenant=tenant,
                **get_branch_filter(request, tenant)
            )
        except Member.DoesNotExist:
            return JsonResponse({
                "success": False,
                "error": "Member not found or access denied."
            }, status=404)

        if not member.is_paused:
            return JsonResponse({
                "success": False,
                "error": "Member is not currently paused."
            }, status=400)

        pause = MemberPause.objects.select_for_update().filter(
            tenant=tenant,
            member=member,
            end_date__isnull=True
        ).order_by("-start_date").first()

        if pause is None:
            return JsonResponse({
                "success": False,
                "error": (
                    "Active pause record not found. "
                    "Administrator assistance is required."
                )
            }, status=400)

        if resume_date <= pause.start_date:
            return JsonResponse({
                "success": False,
                "error": "Resume date must be after the pause start date."
            }, status=400)

        if not member.plan:
            return JsonResponse({
                "success": False,
                "error": "Member does not have a membership plan."
            }, status=400)

        if member.plan.tenant_id != tenant.id:
            return JsonResponse({
                "success": False,
                "error": "Member plan does not belong to this tenant."
            }, status=400)

        actual_paused_days = (resume_date - pause.start_date).days

        # Credit only the days permitted by this pause record.
        credited_days = min(actual_paused_days, pause.allowed_days)

        policy = get_pause_policy(member)
        _, _, previously_used_days = get_membership_pause_usage(member)

        if previously_used_days + credited_days > policy["max_days"]:
            return JsonResponse({
                "success": False,
                "error": "Total credited pause days exceed the membership allowance.",
                "max_pause_days": policy["max_days"],
                "used_days": previously_used_days,
                "requested_days": credited_days
            }, status=400)

        # Close the active pause record.
        pause.end_date = resume_date
        pause.paused_days = credited_days
        pause.save(update_fields=["end_date", "paused_days"])

        # Extend expiry by credited days only.
        if member.expiry_date:
            member.expiry_date += timedelta(days=credited_days)

        # Recalculate usage after closing the pause.
        _, request_count, used_days = get_membership_pause_usage(member)

        member.is_paused = False
        member.pause_start_date = None
        member.pause_expiry_date = None
        member.used_pause_days = used_days

        # Recalculate status using the existing 7-day expiry rule.
        if member.expiry_date and member.expiry_date < today:
            days_expired = (today - member.expiry_date).days
            member.status = "Expired" if days_expired <= 7 else "Blocked"
        else:
            member.status = "Active"

        member.save(update_fields=[
            "expiry_date",
            "is_paused",
            "pause_start_date",
            "pause_expiry_date",
            "used_pause_days",
            "status"
        ])

    return JsonResponse({
        "success": True,
        "message": "Member resumed successfully.",
        "actual_paused_days": actual_paused_days,
        "credited_pause_days": credited_days,
        "used_pause_days": used_days,
        "remaining_pause_days": max(
            0, policy["max_days"] - used_days
        ),
        "pause_requests_used": request_count,
        "remaining_pause_requests": max(
            0, policy["max_requests"] - request_count
        ),
        "new_expiry_date": (
            member.expiry_date.isoformat()
            if member.expiry_date else None
        ),
        "status": member.status,
        "is_paused": member.is_paused
    })

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def renew_member(request, member_id):
    tenant = get_tenant(request)

    if tenant is None:
        return JsonResponse({
            "success": False,
            "error": "User is not assigned to a tenant."
        }, status=403)

    if request.user.role == "STAFF":
        return JsonResponse({
            "success": False,
            "error": "Staff members are not allowed to renew members."
        }, status=403)

    plan_id = request.data.get("plan")

    if not plan_id:
        return JsonResponse({
            "success": False,
            "error": "Plan is required."
        }, status=400)

    try:
        plan = Plan.objects.get(
            id=plan_id,
            tenant=tenant
        )
    except (Plan.DoesNotExist, ValueError, TypeError):
        return JsonResponse({
            "success": False,
            "error": "Invalid plan for this tenant."
        }, status=400)

    try:
        duration = int(plan.duration)
    except (ValueError, TypeError):
        return JsonResponse({
            "success": False,
            "error": "Invalid plan duration."
        }, status=400)

    if duration <= 0:
        return JsonResponse({
            "success": False,
            "error": "Plan duration must be greater than zero."
        }, status=400)

    today = timezone.localdate()

    with transaction.atomic():
        try:
            member = Member.objects.select_for_update().get(
                id=member_id,
                tenant=tenant,
                **get_branch_filter(request, tenant)
            )
        except Member.DoesNotExist:
            return JsonResponse({
                "success": False,
                "error": "Member not found or access denied."
            }, status=404)

        if member.is_paused:
            return JsonResponse({
                "success": False,
                "error": "Resume the member before renewing the membership."
            }, status=400)

        # Preserve the existing early-renewal behavior.
        if member.expiry_date and member.expiry_date >= today:
            new_expiry_date = (
                member.expiry_date + timedelta(days=duration)
            )
        else:
            new_expiry_date = today + timedelta(days=duration)

        # Start a new pause-allowance cycle.
        member.plan = plan
        member.expiry_date = new_expiry_date
        member.membership_start_date = today
        member.used_pause_days = 0

        # Clear pause state defensively.
        member.is_paused = False
        member.pause_start_date = None
        member.pause_expiry_date = None
        member.status = "Active"

        member.save(update_fields=[
            "plan",
            "expiry_date",
            "membership_start_date",
            "used_pause_days",
            "is_paused",
            "pause_start_date",
            "pause_expiry_date",
            "status"
        ])

    policy = get_pause_policy(member)

    return JsonResponse({
        "success": True,
        "message": "Plan renewed successfully.",
        "member_id": member.id,
        "member_name": member.name,
        "plan": {
            "id": plan.id,
            "name": plan.name,
            "duration": plan.duration,
            "price": plan.price
        },
        "membership_start_date": member.membership_start_date.isoformat(),
        "new_expiry_date": member.expiry_date.isoformat(),
        "pause_policy": policy,
        "status": member.status
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_member_payment(request, member_id):
    tenant = get_tenant(request)

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
        branch=member.branch,
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

# ============================================================
# ENQUIRY
# ============================================================

from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_enquiry(request):
    tenant = get_tenant(request)

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403,
        )

    name = request.data.get("name", "").strip()
    phone = request.data.get("phone", "").strip()
    plan = request.data.get("plan") or None
    edate = request.data.get("date") or None

    if not name:
        return JsonResponse({"error": "Name is required"}, status=400)

    if not (phone.isdigit() and len(phone) == 10):
        return JsonResponse(
            {"error": "Enter a valid 10-digit mobile number"},
            status=400,
        )

    role = request.user.role

    if role == "TENANT_ADMIN":
        branch_id = request.data.get("branch_id")

        if not branch_id:
            return JsonResponse(
                {"error": "Please select a branch"},
                status=400,
            )

        branch = get_object_or_404(
            Branch,
            id=branch_id,
            tenant=tenant,
        )

    elif role in ["BRANCH_ADMIN", "STAFF"]:
        branch = getattr(request.user, "branch", None)

        if branch is None or branch.tenant_id != tenant.id:
            return JsonResponse(
                {"error": "User is not assigned to a valid branch"},
                status=403,
            )

    else:
        return JsonResponse(
            {"error": "You are not allowed to add enquiries"},
            status=403,
        )

    enquiry = Enquiry.objects.create(
        tenant=tenant,
        branch=branch,
        name=name,
        phone=phone,
        plan=plan,
        date=edate,
    )

    return JsonResponse({
        "message": "Enquiry added",
        "id": enquiry.id,
        "name": enquiry.name,
        "phone": enquiry.phone,
        "plan": enquiry.plan,
        "date": enquiry.date,
        "branch_id": enquiry.branch_id,
        "branch_name": branch.name,
    }, status=201)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def view_enquiry(request):
    tenant = get_tenant(request)

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403,
        )

    enquiries = Enquiry.objects.filter(tenant=tenant)

    role = request.user.role

    if role in ["BRANCH_ADMIN", "STAFF"]:
        branch = getattr(request.user, "branch", None)

        if branch is None or branch.tenant_id != tenant.id:
            return JsonResponse(
                {"error": "User is not assigned to a valid branch"},
                status=403,
            )

        enquiries = enquiries.filter(branch=branch)

    elif role == "TENANT_ADMIN":
        branch_id = request.query_params.get("branch_id")

        if branch_id:
            enquiries = enquiries.filter(branch_id=branch_id)

    data = [
        {
            "id": e.id,
            "name": e.name,
            "phone": e.phone,
            "plan": e.plan,
            "date": e.date,
            "branch_id": e.branch_id,
            "branch_name": e.branch.name if e.branch else None,
        }
        for e in enquiries.order_by("-id")
    ]

    return JsonResponse(data, safe=False)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_enquiry(request, enquiry_id):
    tenant = get_tenant(request)

    if tenant is None:
        return JsonResponse(
            {"error": "User is not assigned to a tenant"},
            status=403,
        )

    if request.user.role not in ["TENANT_ADMIN", "BRANCH_ADMIN"]:
        return JsonResponse(
            {"error": "You are not allowed to delete enquiries"},
            status=403,
        )

    enquiry = get_object_or_404(
        Enquiry,
        id=enquiry_id,
        tenant=tenant,
    )

    if request.user.role == "BRANCH_ADMIN":
        branch = getattr(request.user, "branch", None)

        if branch is None or enquiry.branch_id != branch.id:
            return JsonResponse(
                {"error": "You cannot delete this enquiry"},
                status=403,
            )

    enquiry.delete()

    return JsonResponse({
        "message": "Enquiry deleted successfully",
    })

# ============================================================
# EXPENSES / INCOME (manual entries + reports)
# ============================================================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def expenses(request):

    tenant = get_tenant(request)

    if tenant is None:
        return JsonResponse({
            "error": "User is not assigned to a tenant"
        }, status=403)

    qs = (
        Expense.objects
        .filter(tenant=tenant)
        .select_related("branch")
        .order_by("-date", "-id")
    )

    # ----------------------------------
    # BRANCH ADMIN / STAFF
    # ----------------------------------

    if request.user.role in [
        "BRANCH_ADMIN",
        "STAFF"
    ]:

        if not request.user.branch_id:
            return JsonResponse({
                "error": "User is not assigned to a branch"
            }, status=403)

        qs = qs.filter(
            branch_id=request.user.branch_id
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

            "branch": (
                {
                    "id": e.branch.id,
                    "name": e.branch.name,
                    "location": e.branch.location,
                }
                if e.branch
                else None
            ),

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
def add_expense(request):

    tenant = get_tenant(request)

    if tenant is None:
        return JsonResponse({
            "error": "User is not assigned to a tenant"
        }, status=403)

    # Tenant Admin, Branch Admin and Staff can add expenses
    if request.user.role not in [
        "TENANT_ADMIN",
        "BRANCH_ADMIN",
        "STAFF"
    ]:
        return JsonResponse({
            "error": "You do not have permission to add expenses"
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

    # ----------------------------------
    # BRANCH
    # ----------------------------------

    if request.user.role in [
        "BRANCH_ADMIN",
        "STAFF"
    ]:

        if not request.user.branch_id:
            return JsonResponse({
                "error": "User is not assigned to a branch"
            }, status=403)

        branch = request.user.branch

    else:
        branch_id = data.get("branch_id")

        if not branch_id:
            return JsonResponse({
                "error": "Branch is required"
            }, status=400)

        try:
            branch = Branch.objects.get(
                id=branch_id,
                tenant=tenant
            )
        except Branch.DoesNotExist:
            return JsonResponse({
                "error": "Invalid branch"
            }, status=404)

    expense = Expense.objects.create(
        tenant=tenant,
        branch=branch,
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


import json

from django.http import JsonResponse


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_staff_payment(request, staff_id):

    tenant = get_tenant(request)

    if tenant is None:
        return JsonResponse({
            "error": "User is not assigned to a tenant"
        }, status=403)

    # ----------------------------------
    # PERMISSION
    # ----------------------------------

    if request.user.role not in [
        "TENANT_ADMIN",
        "BRANCH_ADMIN"
    ]:
        return JsonResponse({
            "error": "Only Tenant Admin and Branch Admin can record staff payments"
        }, status=403)

    # ----------------------------------
    # PARSE JSON
    # ----------------------------------

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({
            "error": "Invalid JSON data"
        }, status=400)

    # ----------------------------------
    # GET STAFF
    # ----------------------------------

    try:
        staff = (
            Staffs.objects
            .select_related("branch")
            .get(
                id=staff_id,
                tenant=tenant,
                **get_branch_filter(request, tenant)
            )
        )
    except Staffs.DoesNotExist:
        return JsonResponse({
            "error": "Staff not found or access denied"
        }, status=404)

    # ----------------------------------
    # AMOUNT
    # ----------------------------------

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

    # ----------------------------------
    # PAYMENT DATE
    # ----------------------------------

    payment_date = data.get("payment_date")

    if not payment_date:
        return JsonResponse({
            "error": "Payment date is required"
        }, status=400)

    # ----------------------------------
    # PAYMENT METHOD
    # ----------------------------------

    payment_method = data.get("payment_method")

    if not payment_method:
        return JsonResponse({
            "error": "Payment method is required"
        }, status=400)

    # ----------------------------------
    # PAYMENT TYPE
    # ----------------------------------

    payment_type = data.get(
        "payment_type",
        "Salary"
    )

    # ----------------------------------
    # DESCRIPTION
    # ----------------------------------

    description = data.get(
        "description",
        ""
    )

    # ----------------------------------
    # CREATE PAYMENT
    # ----------------------------------

    payment = Payment.objects.create(
        tenant=tenant,
        staff=staff,
        amount=amount,
        payment_type=payment_type,
        payment_method=payment_method,
        payment_date=payment_date,
    )

    # ----------------------------------
    # CREATE EXPENSE
    # ----------------------------------

    expense = Expense.objects.create(
        tenant=tenant,
        branch=staff.branch,

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

    # ----------------------------------
    # RETURN
    # ----------------------------------

    return JsonResponse({
        "message": "Staff payment recorded successfully",

        "payment_id": payment.id,
        "expense_id": expense.id,

        "staff_id": staff.id,
        "staff_name": staff.name,

        "amount": f"{payment.amount:.2f}",

        "payment_type": payment_type,

        "branch": {
            "id": staff.branch.id,
            "name": staff.branch.name
        } if staff.branch else None,

    }, status=201)


# @api_view(["GET"])
# @permission_classes([IsAuthenticated])
# def view_expenses(request):

#     tenant = get_tenant(request)

#     if tenant is None:
#         return JsonResponse({
#             "error": "User is not assigned to a tenant"
#         }, status=403)

#     qs = (
#         Expense.objects
#         .filter(tenant=tenant)
#         .select_related("branch")
#         .order_by("-date", "-id")
#     )

#     # ----------------------------------
#     # BRANCH ADMIN / STAFF
#     # ----------------------------------

#     if request.user.role in [
#         "BRANCH_ADMIN",
#         "STAFF"
#     ]:

#         if not request.user.branch_id:
#             return JsonResponse({
#                 "error": "User is not assigned to a branch"
#             }, status=403)

#         qs = qs.filter(
#             branch_id=request.user.branch_id
#         )

#     data = [
#         {
#             "id": e.id,
#             "title": e.title,
#             "name": e.name,
#             "phone": e.phone,
#             "category": e.category,
#             "description": e.description,
#             "amount": str(e.amount),
#             "payment_method": e.payment_method,
#             "date": e.date.strftime("%Y-%m-%d"),
#             "branch": (
#                 {
#                     "id": e.branch.id,
#                     "name": e.branch.name,
#                     "location": e.branch.location,
#                 }
#                 if e.branch
#                 else None
#             ),
#             "type": (
#                 "Salary"
#                 if e.is_system_generated
#                 else "Additional"
#             ),
#         }
#         for e in qs
#     ]

#     return JsonResponse(data, safe=False)

    
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_income(request):
    tenant = get_tenant(request)

    if tenant is None:
        return JsonResponse({
            "error": "User is not assigned to a tenant"
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

    # Determine branch
    branch = None

    if request.user.role in ["BRANCH_ADMIN", "STAFF"]:
        if not request.user.branch_id:
            return JsonResponse({
                "error": "User is not assigned to a branch"
            }, status=403)

        branch = request.user.branch

    elif data.get("branch_id"):
        try:
            branch = Branch.objects.get(
                id=data.get("branch_id"),
                tenant=tenant
            )
        except Branch.DoesNotExist:
            return JsonResponse({
                "error": "Branch not found or access denied"
            }, status=404)

    # Create additional income
    income = Income.objects.create(
        tenant=tenant,
        branch=branch,
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
        .select_related(
            "member",
            "member__branch",
            "branch"
        )
        .order_by("-date", "-id")
    )

    # Branch-level filtering
    if request.user.role in ["BRANCH_ADMIN", "STAFF"]:
        if not request.user.branch_id:
            return JsonResponse({
                "error": "User is not assigned to a branch"
            }, status=403)

        from django.db.models import Q

        income_qs = income_qs.filter(
            Q(member__branch_id=request.user.branch_id)
            |
            Q(branch_id=request.user.branch_id)
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
    if request.user.role in ["BRANCH_ADMIN", "STAFF"]:
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

    # -------------------------
    # SORT ALL INCOME
    # -------------------------

    data.sort(
        key=lambda x: x["_sort_date"],
        reverse=True
    )

    for item in data:
        item.pop("_sort_date", None)

    return JsonResponse(data, safe=False)

from django.db.models import Sum


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def income_by_members(request):

    tenant = get_tenant(request)

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

    # --------------------------------------------------
    # MEMBERSHIP + ADDITIONAL INCOME
    # --------------------------------------------------

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
            "member__branch",
            "branch"
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

        # Membership income has member -> branch
        # Additional income has branch directly
        from django.db.models import Q

        base_income = base_income.filter(
            Q(
                member__branch_id=request.user.branch_id
            )
            |
            Q(
                branch_id=request.user.branch_id
            )
        )

    # --------------------------------------------------
    # MEMBERSHIP INCOME BY PLAN
    # --------------------------------------------------

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

    # --------------------------------------------------
    # ADDITIONAL INCOME
    # --------------------------------------------------

    additional_income = (
        base_income
        .filter(
            is_system_generated=False
        )
        .exclude(
            category="membership"
        )
        .aggregate(
            total=Sum("amount")
        )["total"] or 0
    )

    # --------------------------------------------------
    # PRODUCT SALES
    # --------------------------------------------------

    sales_qs = (
        Sales_product.objects
        .filter(
            tenant=tenant,
            sold_at__date__gte=start_date,
            sold_at__date__lte=end_date
        )
        .select_related(
            "member",
            "member__branch",
            "product"
        )
    )

    # Branch restriction for product sales
    if request.user.role in [
        "BRANCH_ADMIN",
        "STAFF"
    ]:
        sales_qs = sales_qs.filter(
            member__branch_id=request.user.branch_id
        )

    product_sales = (
        sales_qs
        .aggregate(
            total=Sum("total_amount")
        )["total"] or 0
    )

    # --------------------------------------------------
    # RESPONSE
    # --------------------------------------------------

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
                "name": "Product Sales",
                "amount": float(product_sales)
            },
            {
                "name": "Additional Income",
                "amount": float(additional_income)
            },
        ],
    })

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def expense_by_category(request):

    tenant = get_tenant(request)

    # -----------------------------------------
    # TENANT
    # -----------------------------------------

    if tenant is None:
        return JsonResponse(
            {
                "error":
                    "User is not assigned to a tenant"
            },
            status=403
        )

    # -----------------------------------------
    # PERIOD
    # -----------------------------------------

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
            {
                "error": "Invalid period"
            },
            status=400
        )

    # -----------------------------------------
    # EXPENSES
    # -----------------------------------------

    expenses = Expense.objects.filter(
        tenant=tenant,
        date__gte=start_date,
        date__lte=end_date
    )

    # -----------------------------------------
    # BRANCH ADMIN / STAFF
    # -----------------------------------------

    if request.user.role in [
        "BRANCH_ADMIN",
        "STAFF"
    ]:

        if not request.user.branch_id:
            return JsonResponse(
                {
                    "error":
                        "User is not assigned to a branch"
                },
                status=403
            )

        expenses = expenses.filter(
            branch_id=request.user.branch_id
        )

    # -----------------------------------------
    # CATEGORY
    # -----------------------------------------

    qs = (
        expenses
        .values("category")
        .annotate(
            total=Sum("amount")
        )
        .order_by("-total")
    )

    data = [
        {
            "category": expense["category"],
            "amount": float(
                expense["total"] or 0
            )
        }
        for expense in qs
    ]

    return JsonResponse(
        {
            "success": True,
            "period": period,
            "start_date": start_date.strftime(
                "%Y-%m-%d"
            ),
            "end_date": end_date.strftime(
                "%Y-%m-%d"
            ),
            "expenses": data,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def profit_loss_report(request):

    tenant = get_tenant(request)

    # -----------------------------------------
    # TENANT
    # -----------------------------------------

    if tenant is None:
        return JsonResponse(
            {
                "error":
                    "User is not assigned to a tenant"
            },
            status=403
        )

    # -----------------------------------------
    # PERIOD
    # -----------------------------------------

    period = request.GET.get("period")

    selected_date = request.GET.get("date")

    from_date = request.GET.get("from_date")

    to_date = request.GET.get("to_date")

    try:

        if from_date and to_date:

            start_date = datetime.strptime(
                from_date,
                "%Y-%m-%d"
            ).date()

            end_date = datetime.strptime(
                to_date,
                "%Y-%m-%d"
            ).date()

        else:

            start_date, end_date = get_period_dates(
                period,
                selected_date
            )

    except ValueError:

        return JsonResponse(
            {
                "error":
                    "Invalid date format. Use YYYY-MM-DD"
            },
            status=400
        )

    if start_date is None:

        return JsonResponse(
            {
                "error": "Invalid period"
            },
            status=400
        )

    # -----------------------------------------
    # BRANCH
    # -----------------------------------------

    branch_id = None

    if request.user.role in [
        "BRANCH_ADMIN",
        "STAFF"
    ]:

        if not request.user.branch_id:

            return JsonResponse(
                {
                    "error":
                        "User is not assigned to a branch"
                },
                status=403
            )

        branch_id = request.user.branch_id

    # =====================================================
    # INCOME
    # =====================================================

    incomes_qs = (
        Income.objects
        .filter(
            tenant=tenant,
            date__date__gte=start_date,
            date__date__lte=end_date
        )
        .select_related(
            "member",
            "member__branch"
        )
    )

    # Branch restriction
    if branch_id:

        incomes_qs = incomes_qs.filter(
            member__branch_id=branch_id
        )

    income_members = []

    total_membership_income = 0

    for income in incomes_qs:

        amount = float(
            income.amount
        )

        total_membership_income += amount

        income_members.append(
            {
                "member": (
                    income.member.name
                    if income.member
                    else "-"
                ),
                "amount": amount,
                "payment_method":
                    income.payment_method,
                "date":
                    income.date.strftime(
                        "%d-%m-%Y"
                    ),
            }
        )

    # =====================================================
    # PRODUCT SALES
    # =====================================================

    sales_qs = (
        Sales_product.objects
        .filter(
            tenant=tenant,
            sold_at__date__gte=start_date,
            sold_at__date__lte=end_date
        )
        .select_related(
            "member",
            "member__branch",
            "product"
        )
    )

    # Branch restriction
    if branch_id:

        sales_qs = sales_qs.filter(
            member__branch_id=branch_id
        )

    sales_list_data = []

    sales_category = {}

    total_sales = 0

    for sale in sales_qs:

        amount = float(
            sale.total_amount
        )

        total_sales += amount

        category = (
            sale.product.category
            or "Other"
        )

        sales_category[category] = (
            sales_category.get(
                category,
                0
            ) + amount
        )

        sales_list_data.append(
            {
                "member": (
                    sale.member.name
                    if sale.member
                    else "-"
                ),
                "product":
                    sale.product.name,
                "category":
                    category,
                "quantity":
                    sale.quantity,
                "amount":
                    amount,
                "date":
                    sale.sold_at.strftime(
                        "%d-%m-%Y %H:%M"
                    ),
            }
        )

    # =====================================================
    # EXPENSES
    # =====================================================

    expenses_qs = (
        Expense.objects
        .filter(
            tenant=tenant,
            date__gte=start_date,
            date__lte=end_date
        )
    )

    # Branch restriction
    if branch_id:

        expenses_qs = expenses_qs.filter(
            branch_id=branch_id
        )

    expense_list_data = []

    expense_category = {}

    total_expense = 0

    for expense in expenses_qs:

        amount = float(
            expense.amount
        )

        total_expense += amount

        category = (
            expense.category
            or "Other"
        )

        expense_category[category] = (
            expense_category.get(
                category,
                0
            ) + amount
        )

        expense_list_data.append(
            {
                "category":
                    category,
                "amount":
                    amount,
                "date":
                    expense.date.strftime(
                        "%d-%m-%Y"
                    ),
                "description":
                    expense.description,
            }
        )

    # =====================================================
    # PROFIT / LOSS
    # =====================================================

    total_income = (
        total_membership_income
        + total_sales
    )

    net_profit = (
        total_income
        - total_expense
    )

    return JsonResponse(
        {
            "success": True,

            "period":
                period,

            "start_date":
                start_date.strftime(
                    "%Y-%m-%d"
                ),

            "end_date":
                end_date.strftime(
                    "%Y-%m-%d"
                ),

            "kpis": {
                "membership_income":
                    total_membership_income,

                "product_sales":
                    total_sales,

                "total_income":
                    total_income,

                "total_expense":
                    total_expense,

                "net_profit":
                    net_profit,
            },

            "sales_category":
                sales_category,

            "expense_category":
                expense_category,

            "income_members":
                income_members,

            "sales":
                sales_list_data,

            "expenses":
                expense_list_data,
        }
    )

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


def normalize_equipment_name(name: str) -> str:
    """
    Normalizes equipment names to standard canonical names,
    handling common typos, casing, and singular/plural variations.
    E.g. 'Dumbells', 'dumbell', 'dumbbell', 'dumbbells' -> 'Dumbbells'
         'cables', 'cable' -> 'Cables'
    """
    if not name:
        return ""
    cleaned = name.strip()
    lower = cleaned.lower()
    if "dumbell" in lower or "dumbbell" in lower:
        return "Dumbbells"
    if "cable" in lower:
        return "Cables"
    if "barbell" in lower or "barbel" in lower:
        return "Barbells"
    if "kettlebell" in lower or "kettle bell" in lower:
        return "Kettlebells"
    if "bench" in lower:
        return "Bench"
    if "resistance band" in lower or "band" in lower:
        return "Resistance Bands"
    return cleaned


def is_dumbbell_equipment(name: str) -> bool:
    if not name:
        return False
    lower = name.lower()
    return "dumbbell" in lower or "dumbell" in lower


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_workout(request):
    import json
    import logging
    from datetime import date

    logger = logging.getLogger(__name__)

    # ---------------------------------------------------------
    # TENANT
    # ---------------------------------------------------------
    tenant = get_tenant(request)

    if tenant is None:
        return Response(
            {"success": False, "error": "User is not assigned to a tenant."},
            status=status.HTTP_403_FORBIDDEN
        )

    # ---------------------------------------------------------
    # MEMBER ID AND EXPERIENCE LEVEL
    # ---------------------------------------------------------
    member_id = request.data.get("member_id")

    if not member_id:
        return Response(
            {"success": False, "error": "Member ID is required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    experience_level = str(
        request.data.get("experience_level", "beginner")
    ).strip().lower()

    allowed_levels = ["beginner", "intermediate", "advanced"]

    if experience_level not in allowed_levels:
        return Response(
            {
                "success": False,
                "error": "Choose beginner, intermediate or advanced."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    # ---------------------------------------------------------
    # MEMBER ACCESS
    # ---------------------------------------------------------
    member_filter = {
        "id": member_id,
        "tenant": tenant
    }

    if request.user.role in ["BRANCH_ADMIN", "STAFF"]:
        if not request.user.branch_id:
            return Response(
                {"success": False, "error": "User is not assigned to a branch."},
                status=status.HTTP_403_FORBIDDEN
            )

        member_filter["branch_id"] = request.user.branch_id

    try:
        member = (
            Member.objects
            .select_related("branch", "plan")
            .get(**member_filter)
        )
    except Member.DoesNotExist:
        return Response(
            {"success": False, "error": "Member not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    member_branch = member.branch

    if member_branch is None:
        return Response(
            {"success": False, "error": "Member is not assigned to a branch."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # ---------------------------------------------------------
    # GET EQUIPMENT FOR THIS MEMBER'S BRANCH
    # ---------------------------------------------------------
    equipment_queryset = (
        GymEquipment.objects
        .filter(
            tenant=tenant,
            branch=member_branch,
            is_available=True
        )
        .order_by("name", "weight")
    )

    equipment_list = []

    for item in equipment_queryset:
        equipment_data = {
            "name": item.name,
            "quantity": item.quantity
        }

        if item.weight is not None:
            equipment_data["weight_kg"] = float(item.weight)

        equipment_list.append(equipment_data)

    logger.info(
        "Workout equipment lookup: tenant=%s branch=%s equipment=%s",
        tenant.pk,
        member_branch.pk,
        equipment_list
    )

    # ---------------------------------------------------------
    # REUSE SAVED WORKOUT PLAN
    # Reuse saved plan ONLY when member.workout_experience_level == requested experience_level.
    # If the requested level differs, or stored level is blank/missing, generate a new plan.
    # ---------------------------------------------------------
    if (
        member.workout_plan
        and member.workout_experience_level
        and member.workout_experience_level.strip().lower() == experience_level
    ):
        return Response(
            {
                "success": True,
                "message": "Saved workout plan loaded successfully.",
                "current_workout_day": member.current_workout_day,
                "experience_level": member.workout_experience_level,
                "available_equipment": equipment_list,
                "workout_plan": member.workout_plan,
                "plan_reused": True
            },
            status=status.HTTP_200_OK
        )

    # ---------------------------------------------------------
    # PAUSED-MEMBERSHIP CHECK
    # Check paused-membership logic before generating a new or replacement plan.
    # ---------------------------------------------------------
    auto_resume_member(member, date.today())
    if member.is_paused:
        return Response(
            {
                "success": False,
                "error": (
                    "Member is currently paused. "
                    "Resume the membership before generating a new plan."
                )
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    # ---------------------------------------------------------
    # FORMAT EQUIPMENT FOR AI & DETECT AVAILABLE EQUIPMENT
    # Fix equipment-name normalization (e.g. 'Dumbells' -> 'Dumbbells')
    # ---------------------------------------------------------
    if equipment_list:
        equipment_lines = []

        for item in equipment_list:
            canonical_name = normalize_equipment_name(item["name"])
            line = (
                f"- {canonical_name} "
                f"(Quantity: {item['quantity']}"
            )

            if "weight_kg" in item:
                line += f", Weight: {item['weight_kg']} kg"

            line += ")"
            equipment_lines.append(line)

        equipment_text = "\n".join(equipment_lines)
    else:
        equipment_text = "NO GYM EQUIPMENT IS CURRENTLY AVAILABLE."

    # Recognize available equipment with spelling normalization
    has_dumbbells = any(
        is_dumbbell_equipment(item["name"])
        for item in equipment_list
    )
    has_cables = any(
        "cable" in item["name"].lower()
        for item in equipment_list
    )
    has_barbells = any(
        "barbell" in item["name"].lower() or "barbel" in item["name"].lower()
        for item in equipment_list
    )
    has_bench = any(
        "bench" in item["name"].lower()
        for item in equipment_list
    )
    has_kettlebells = any(
        "kettlebell" in item["name"].lower() or "kettle bell" in item["name"].lower()
        for item in equipment_list
    )

    dumbbell_weights = [
        item["weight_kg"]
        for item in equipment_list
        if is_dumbbell_equipment(item["name"]) and "weight_kg" in item
    ]
    max_dumbbell_weight_text = f"{max(dumbbell_weights)} kg" if dumbbell_weights else "the available weight"

    # ---------------------------------------------------------
    # MEMBER DETAILS
    # ---------------------------------------------------------
    goal = getattr(member, "goal", None) or "General Fitness"
    age = getattr(member, "age", None)
    gender = getattr(member, "gender", None) or "Not specified"
    height = getattr(member, "height", None)
    weight = getattr(member, "weight", None)

    # ---------------------------------------------------------
    # GROQ CLIENT
    # ---------------------------------------------------------
    try:
        from groq import Groq
        client = Groq(api_key=settings.GROQ_API_KEY)
    except Exception:
        logger.exception("Groq client initialization failed.")

        return Response(
            {"success": False, "error": "Unable to initialize AI service."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    # ---------------------------------------------------------
    # AI PROMPT
    # ---------------------------------------------------------
    prompt = f"""
You are a professional gym workout planner.

Generate a personalized workout plan containing EXACTLY 6 days tailored specifically for a {experience_level.upper()} trainee.

MEMBER DETAILS
--------------
Goal: {goal}
Age: {age}
Gender: {gender}
Height: {height} cm
Body weight: {weight} kg
Experience Level: {experience_level}

ACTUAL EQUIPMENT AVAILABLE IN THE MEMBER'S BRANCH
-------------------------------------------------
{equipment_text}

MANDATORY EQUIPMENT RULES
-------------------------
1. Use ONLY equipment listed above, plus safe bodyweight floor/standing exercises.
2. The equipment inventory listed above is the ABSOLUTE SOURCE OF TRUTH.
3. NEVER assume unlisted equipment is available. NEVER generate exercises that require unavailable equipment:
   - Barbells are STRICTLY PROHIBITED unless listed in the inventory above.
   - Benches (flat/incline/decline bench) are STRICTLY PROHIBITED unless listed above. If no bench is listed, prescribe floor variations (e.g., Dumbbell Floor Press instead of Bench Press).
   - Kettlebells, resistance bands, pull-up bars, smith machines, and leg machines are STRICTLY PROHIBITED unless listed above.
4. Consider the listed quantity and exact weight:
   - For dumbbells: Never recommend a weight heavier than the available weight ({max_dumbbell_weight_text}).
5. If dumbbells are available, incorporate dumbbell exercises as primary resistance exercises throughout the plan.
6. If cables are available, incorporate cable exercises (e.g., Cable Pushdowns, Cable Curls, Cable Face Pulls, Cable Rows, Cable Chest Flyes).
7. If only dumbbells and cables are available, plan exercises using ONLY dumbbells, cables, and bodyweight floor/standing movements.
8. If no equipment is available, generate a safe, structured bodyweight plan.
9. Do not claim that an exercise uses a weight different from the actual equipment available.
10. A listed quantity is inventory information, not a prescribed number of sets or repetitions.

EXPERIENCE LEVEL REQUIREMENTS ({experience_level.upper()})
---------------------------------------------------------
The experience level must fundamentally determine exercise selection, movement complexity, variations, sets, reps, and training volume across all 6 days:

- Beginner:
  * Exercise Selection & Variations: Focus on fundamental, accessible, simple movements with high stability (e.g., standard Dumbbell Floor Press, Goblet Squats, Standing Dumbbell Bicep Curls, Dumbbell Shoulder Press, Cable Rows/Pushdowns with stable stance, standard Bodyweight Squats, Glute Bridges, Knee/Standard Push-ups). Avoid complex or high-injury-risk unilateral variations.
  * Form Priorities: Clear emphasis on proper movement patterns, joint control, and basic mind-muscle connection.
  * Volume & Reps: Lower, manageable volume. Typically 2 to 3 sets per exercise, 8 to 12 reps with controlled tempo, with 3 to 4 exercises per day.

- Intermediate:
  * Exercise Selection & Variations: Moderate-to-challenging movements combining compound lifts and focused isolation exercises (e.g., Dumbbell Romanian Deadlifts, Dumbbell Walking Lunges, Dumbbell Lateral Raises, Cable Crossover Flyes, Cable Lateral Raises, Cable Face Pulls).
  * Form Priorities: Progressive overload, mind-muscle connection, and controlled eccentric tempo.
  * Volume & Reps: Moderate volume. Typically 3 to 4 sets per exercise, 10 to 15 reps (or 8-12 for compound, 12-15 for isolation), with 4 to 5 exercises per day.

- Advanced:
  * Exercise Selection & Variations: Challenging variations, demanding compound movements, and unilateral/stability challenges (e.g., Bulgarian Split Squats, Single-leg Romanian Deadlifts, 1.5-rep or tempo Dumbbell Floor Press, Cable Cross-body Extensions, explosive or paused variations).
  * Form Priorities: High intensity, peak contraction, advanced mechanical tension, and strict execution under fatigue.
  * Volume & Reps: Higher training volume and intensity. Typically 4 to 5 sets per exercise, varied periodized rep ranges (e.g., 6-10 for heavy compound, 12-20 for hypertrophy/burnout), with 5 to 6 exercises per day.

DUMBBELL EXAMPLES
-----------------
When compatible with the available equipment, consider:
- Dumbbell Floor Press
- Dumbbell One Arm Row
- Dumbbell Bicep Curl
- Dumbbell Hammer Curl
- Dumbbell Shoulder Press
- Dumbbell Lateral Raise
- Dumbbell Goblet Squat
- Dumbbell Romanian Deadlift
- Dumbbell Lunges
- Dumbbell Triceps Extension
- Dumbbell Bulgarian Split Squat
- Dumbbell Calf Raise

Choose suitable exercises rather than forcing every example into the plan.

WORKOUT STRUCTURE
-----------------
Create exactly 6 workout days.

Each day must contain:
- day: integer (1 to 6)
- body_part: string describing muscle group(s) targeted (e.g., "Chest + Triceps", "Back + Biceps", "Legs + Core", etc.)
- workouts: list of exercise objects

Each exercise must contain:
- workout_name: string (e.g., "Dumbbell Floor Press")
- sets: integer (e.g., 3)
- reps: string (e.g., "10-12")
- duration: string (e.g., "8 min")

Include suitable exercise variety, manageable volume, appropriate recovery, and exercises aligned with the member's goal and {experience_level} experience level.
Do not prescribe a weight beyond the available equipment.

Return JSON only, using this structure:

{{
  "workout_plan": [
    {{
      "day": 1,
      "body_part": "Chest + Triceps",
      "workouts": [
        {{
          "workout_name": "Dumbbell Floor Press",
          "sets": 3,
          "reps": "10-12",
          "duration": "8 min"
        }}
      ]
    }}
  ]
}}

The example is illustrative. Return all 6 days, with suitable exercises and valid JSON. Do not include Markdown or explanations.
"""

    # ---------------------------------------------------------
    # CALL GROQ
    # ---------------------------------------------------------
    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You generate safe, equipment-aware workout plans for {experience_level} gym members. "
                        "Follow the supplied equipment inventory strictly, never prescribe unavailable equipment, "
                        f"enforce {experience_level}-appropriate exercise selection, sets, and reps, and return valid JSON only."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.2,
            response_format={"type": "json_object"}
        )

        content = response.choices[0].message.content

        if not content:
            raise ValueError("AI returned an empty response.")

        workout_data = json.loads(content)

    except Exception:
        logger.exception("Workout generation failed.")

        return Response(
            {
                "success": False,
                "error": "Failed to generate a valid workout plan."
            },
            status=status.HTTP_502_BAD_GATEWAY
        )

    # ---------------------------------------------------------
    # VALIDATE PLAN STRUCTURE
    # ---------------------------------------------------------
    workout_plan = workout_data.get("workout_plan")

    if not isinstance(workout_plan, list) or len(workout_plan) != 6:
        return Response(
            {
                "success": False,
                "error": "AI must generate exactly 6 workout days."
            },
            status=status.HTTP_502_BAD_GATEWAY
        )

    required_day_fields = ["day", "body_part", "workouts"]
    required_workout_fields = [
        "workout_name", "sets", "reps", "duration"
    ]

    for day_index, day_data in enumerate(workout_plan, start=1):
        if not isinstance(day_data, dict):
            return Response(
                {"success": False, "error": f"Invalid workout day {day_index}."},
                status=status.HTTP_502_BAD_GATEWAY
            )

        if any(field not in day_data for field in required_day_fields):
            return Response(
                {
                    "success": False,
                    "error": f"Missing required fields in workout day {day_index}."
                },
                status=status.HTTP_502_BAD_GATEWAY
            )

        # Enforce sequential day numbering.
        if day_data["day"] != day_index:
            return Response(
                {
                    "success": False,
                    "error": "Workout days must be numbered from 1 to 6."
                },
                status=status.HTTP_502_BAD_GATEWAY
            )

        workouts = day_data["workouts"]

        if not isinstance(workouts, list) or not workouts:
            return Response(
                {
                    "success": False,
                    "error": f"Workout day {day_index} has no exercises."
                },
                status=status.HTTP_502_BAD_GATEWAY
            )

        for workout_index, workout in enumerate(workouts, start=1):
            if not isinstance(workout, dict):
                return Response(
                    {
                        "success": False,
                        "error": (
                            f"Invalid exercise in day {day_index}, "
                            f"exercise {workout_index}."
                        )
                    },
                    status=status.HTTP_502_BAD_GATEWAY
                )

            if any(field not in workout for field in required_workout_fields):
                return Response(
                    {
                        "success": False,
                        "error": (
                            f"Missing exercise fields in day {day_index}, "
                            f"exercise {workout_index}."
                        )
                    },
                    status=status.HTTP_502_BAD_GATEWAY
                )

            if (
                not isinstance(workout["workout_name"], str)
                or not workout["workout_name"].strip()
                or not isinstance(workout["reps"], str)
                or not isinstance(workout["duration"], str)
                or not isinstance(workout["sets"], int)
                or isinstance(workout["sets"], bool)
                or workout["sets"] < 1
            ):
                return Response(
                    {
                        "success": False,
                        "error": (
                            f"Invalid exercise data in day {day_index}, "
                            f"exercise {workout_index}."
                        )
                    },
                    status=status.HTTP_502_BAD_GATEWAY
                )

    # ---------------------------------------------------------
    # EQUIPMENT-AWARE VALIDATION
    # ---------------------------------------------------------
    # 1. Validate that no exercises require unavailable equipment
    unavailable_equipment_detected = []
    for day in workout_plan:
        for workout in day["workouts"]:
            w_name = workout["workout_name"].lower()
            if not has_dumbbells and is_dumbbell_equipment(w_name):
                unavailable_equipment_detected.append(f"Dumbbells in '{workout['workout_name']}'")
            if not has_cables and "cable" in w_name:
                unavailable_equipment_detected.append(f"Cables in '{workout['workout_name']}'")
            if not has_barbells and ("barbell" in w_name or "barbel" in w_name):
                unavailable_equipment_detected.append(f"Barbell in '{workout['workout_name']}'")
            if not has_bench and ("bench" in w_name):
                unavailable_equipment_detected.append(f"Bench in '{workout['workout_name']}'")
            if not has_kettlebells and ("kettlebell" in w_name or "kettle bell" in w_name):
                unavailable_equipment_detected.append(f"Kettlebell in '{workout['workout_name']}'")

    if unavailable_equipment_detected:
        return Response(
            {
                "success": False,
                "error": (
                    f"The AI generated exercises requiring unavailable equipment: "
                    f"{', '.join(unavailable_equipment_detected[:3])}. "
                    f"Please generate the plan again."
                )
            },
            status=status.HTTP_502_BAD_GATEWAY
        )

    # 2. Do not save a plan that completely ignores available dumbbells.
    # Return an error so an incorrect plan is not silently accepted.
    if has_dumbbells:
        dumbbell_exercises = [
            workout
            for day in workout_plan
            for workout in day["workouts"]
            if is_dumbbell_equipment(workout["workout_name"])
        ]

        if not dumbbell_exercises:
            return Response(
                {
                    "success": False,
                    "error": (
                        "The AI generated a plan without dumbbell "
                        "exercises, although dumbbells are available. "
                        "Please generate the plan again."
                    )
                },
                status=status.HTTP_502_BAD_GATEWAY
            )

    # ---------------------------------------------------------
    # SAVE WORKOUT ONLY AFTER VALIDATION
    # ---------------------------------------------------------
    member.workout_plan = workout_plan
    member.workout_experience_level = experience_level
    member.current_workout_day = 1

    member.save(
        update_fields=["workout_plan", "workout_experience_level", "current_workout_day"]
    )

    # ---------------------------------------------------------
    # SUCCESS RESPONSE
    # ---------------------------------------------------------
    return Response(
        {
            "success": True,
            "message": "Workout plan generated successfully.",
            "current_workout_day": member.current_workout_day,
            "experience_level": member.workout_experience_level,
            "available_equipment": equipment_list,
            "workout_plan": member.workout_plan,
            "plan_reused": False
        },
        status=status.HTTP_200_OK
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def complete_workout_day(request, member_id):
    tenant = get_tenant(request)

    if tenant is None:
        return Response(
            {"success": False, "error": "User is not assigned to a tenant."},
            status=status.HTTP_403_FORBIDDEN
        )

    member = get_object_or_404(
        Member,
        id=member_id,
        tenant=tenant,
        **get_branch_filter(request, tenant)
    )

    # Do not allow workout completion while paused
    if member.is_paused:
        return Response(
            {
                "success": False,
                "error": "Member is currently paused."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    if not member.workout_plan:
        return Response(
            {
                "success": False,
                "error": "No workout plan found."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    current_day = member.current_workout_day

    # 6-day plan → after Day 6 start again at Day 1
    if current_day >= 6:
        next_day = 1
    else:
        next_day = current_day + 1

    member.current_workout_day = next_day
    member.save(update_fields=["current_workout_day"])

    return Response({
        "success": True,
        "message": f"Workout Day {current_day} completed.",
        "completed_day": current_day,
        "next_workout_day": next_day
    })
    

# ============================================================
# GYM EQUIPMENT
# ============================================================

from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import GymEquipment, Branch


# -----------------------------------------
# COMMON PERMISSION / QUERY HELPERS
# -----------------------------------------

ALLOWED_EQUIPMENT_ROLES = [
    "TENANT_ADMIN",
    "BRANCH_ADMIN",
    "STAFF",
]


def get_equipment_queryset(request, tenant):
    """
    Tenant Admin: all equipment for the tenant.
    Branch Admin / Staff: equipment for their branch only.
    """
    queryset = (
        GymEquipment.objects
        .filter(tenant=tenant)
        .select_related("branch")
    )

    if request.user.role in ["BRANCH_ADMIN", "STAFF"]:
        if not request.user.branch_id:
            return None

        queryset = queryset.filter(
            branch_id=request.user.branch_id
        )

    return queryset


def get_equipment_branch(request, tenant):
    """
    Tenant Admin selects a branch.
    Branch Admin / Staff use their assigned branch.
    """
    role = request.user.role

    if role in ["BRANCH_ADMIN", "STAFF"]:
        if not request.user.branch_id:
            return None, Response(
                {
                    "success": False,
                    "error": "User is not assigned to a branch.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        return request.user.branch, None

    branch_id = request.data.get("branch_id")

    if not branch_id:
        return None, Response(
            {
                "success": False,
                "error": "Branch is required.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        branch = Branch.objects.get(
            id=branch_id,
            tenant=tenant,
        )
    except (Branch.DoesNotExist, ValueError, TypeError):
        return None, Response(
            {
                "success": False,
                "error": "Invalid branch.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    return branch, None


# -----------------------------------------
# 1. LIST EQUIPMENT
# GET: /gym-equipment/
# -----------------------------------------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_gym_equipment(request):
    tenant = get_tenant(request)

    if tenant is None:
        return Response(
            {
                "success": False,
                "error": "User is not assigned to a tenant.",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.user.role not in ALLOWED_EQUIPMENT_ROLES:
        return Response(
            {
                "success": False,
                "error": "You do not have permission to view equipment.",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    equipment = get_equipment_queryset(request, tenant)

    if equipment is None:
        return Response(
            {
                "success": False,
                "error": "User is not assigned to a branch.",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = GymEquipmentSerializer(
        equipment.order_by("name", "weight"),
        many=True,
    )

    return Response({
        "success": True,
        "equipment": serializer.data,
    })


# -----------------------------------------
# 2. CREATE EQUIPMENT
# POST: /gym-equipment/create/
# -----------------------------------------

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_gym_equipment(request):
    tenant = get_tenant(request)

    if tenant is None:
        return Response(
            {
                "success": False,
                "error": "User is not assigned to a tenant.",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.user.role not in ALLOWED_EQUIPMENT_ROLES:
        return Response(
            {
                "success": False,
                "error": "You do not have permission to create equipment.",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    branch, error_response = get_equipment_branch(
        request,
        tenant,
    )

    if error_response:
        return error_response

    serializer = GymEquipmentSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(
            {
                "success": False,
                "errors": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    equipment = serializer.save(
        tenant=tenant,
        branch=branch,
    )

    return Response(
        {
            "success": True,
            "message": "Equipment added successfully.",
            "equipment": GymEquipmentSerializer(equipment).data,
        },
        status=status.HTTP_201_CREATED,
    )


# -----------------------------------------
# 3. RETRIEVE SINGLE EQUIPMENT
# GET: /gym-equipment/<equipment_id>/
# -----------------------------------------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def retrieve_gym_equipment(request, equipment_id):
    tenant = get_tenant(request)

    if tenant is None:
        return Response(
            {
                "success": False,
                "error": "User is not assigned to a tenant.",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.user.role not in ALLOWED_EQUIPMENT_ROLES:
        return Response(
            {
                "success": False,
                "error": "You do not have permission to view equipment.",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    queryset = get_equipment_queryset(request, tenant)

    if queryset is None:
        return Response(
            {
                "success": False,
                "error": "User is not assigned to a branch.",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    equipment = get_object_or_404(
        queryset,
        id=equipment_id,
    )

    serializer = GymEquipmentSerializer(equipment)

    return Response({
        "success": True,
        "equipment": serializer.data,
    })


# -----------------------------------------
# 4. UPDATE EQUIPMENT
# PUT / PATCH: /gym-equipment/<equipment_id>/update/
# -----------------------------------------

@api_view(["PUT", "PATCH"])
@permission_classes([IsAuthenticated])
def update_gym_equipment(request, equipment_id):
    tenant = get_tenant(request)

    if tenant is None:
        return Response(
            {
                "success": False,
                "error": "User is not assigned to a tenant.",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.user.role not in ALLOWED_EQUIPMENT_ROLES:
        return Response(
            {
                "success": False,
                "error": "You do not have permission to update equipment.",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    queryset = get_equipment_queryset(request, tenant)

    if queryset is None:
        return Response(
            {
                "success": False,
                "error": "User is not assigned to a branch.",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    equipment = get_object_or_404(
        queryset,
        id=equipment_id,
    )

    serializer = GymEquipmentSerializer(
        equipment,
        data=request.data,
        partial=(request.method == "PATCH"),
    )

    if not serializer.is_valid():
        return Response(
            {
                "success": False,
                "errors": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Keep the existing tenant and branch unchanged.
    equipment = serializer.save(
        tenant=tenant,
        branch=equipment.branch,
    )

    return Response({
        "success": True,
        "message": "Equipment updated successfully.",
        "equipment": GymEquipmentSerializer(equipment).data,
    })


# -----------------------------------------
# 5. DELETE EQUIPMENT
# DELETE: /gym-equipment/<equipment_id>/delete/
# -----------------------------------------

@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_gym_equipment(request, equipment_id):
    tenant = get_tenant(request)

    if tenant is None:
        return Response(
            {
                "success": False,
                "error": "User is not assigned to a tenant.",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.user.role not in ALLOWED_EQUIPMENT_ROLES:
        return Response(
            {
                "success": False,
                "error": "You do not have permission to delete equipment.",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.user.role == "STAFF":
        return Response(
            {
                "success": False,
                "error": "Staff cannot delete equipment.",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    queryset = get_equipment_queryset(request, tenant)

    if queryset is None:
        return Response(
            {
                "success": False,
                "error": "User is not assigned to a branch.",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    equipment = get_object_or_404(
        queryset,
        id=equipment_id,
    )

    equipment.delete()

    return Response({
        "success": True,
        "message": "Equipment deleted successfully.",
    })
        

from .models import Member, Income, Expense, Sales_product, Payment, Plan
from .tenant_utils import get_tenant, get_branch_filter


def calculate_growth(current, previous):
    if previous == 0:
        return 100 if current > 0 else 0
    return round(((current - previous) / previous) * 100, 2)


from django.conf import settings
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from .tenant_utils import get_tenant, get_branch_filter
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def sell_product(request):
    tenant = get_tenant(request)

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
        branch=member.branch,
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


from .essl_service import get_all_employee_details


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def essl_test_employees(request):
    try:
        result = get_all_employee_details()
        return Response(result, status=status.HTTP_200_OK)

    except Exception:
        # Do not expose credentials or internal server errors.
        return Response(
            {
                "error": (
                    "Unable to retrieve employees from eSSL. "
                    "Check server logs for details."
                )
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )



from .essl_service import sync_essl_employees

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def essl_sync_employees(request):
    user = request.user
    tenant = getattr(user, "tenant", None)

    if tenant is None:
        return Response(
            {"error": "Your account is not associated with a tenant."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        result = sync_essl_employees(tenant=tenant)
        return Response(result, status=status.HTTP_200_OK)

    except Exception:
        return Response(
            {"error": "eSSL synchronization failed. Check the server logs."},
            status=status.HTTP_502_BAD_GATEWAY,
        )


from .models import BiometricEmployeeMapping, Member, Staffs,Attendance,BiometricDevice
from .serializers import BiometricEmployeeMappingSerializer


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_biometric_mappings(request):
    tenant = get_tenant(request)

    if tenant is None:
        return Response(
            {"error": "User is not assigned to a tenant"},
            status=status.HTTP_403_FORBIDDEN,
        )

    mappings = (
        BiometricEmployeeMapping.objects
        .filter(tenant=tenant)
        .select_related("member", "staff")
        .order_by("essl_employee_code")
    )

    search = request.query_params.get("search", "").strip()

    if search:
        from django.db.models import Q

        mappings = mappings.filter(
            Q(essl_employee_code__icontains=search)
            | Q(essl_employee_name__icontains=search)
        )

    serializer = BiometricEmployeeMappingSerializer(
        mappings,
        many=True,
    )

    return Response(serializer.data)

import logging

from django.db import IntegrityError, transaction
logger = logging.getLogger(__name__)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def link_biometric_employee(request, mapping_id):
    tenant = get_tenant(request)

    if tenant is None:
        return Response(
            {"error": "User is not assigned to a tenant"},
            status=status.HTTP_403_FORBIDDEN,
        )

    member_id = request.data.get("member")
    staff_id = request.data.get("staff")

    # Exactly one non-empty ID must be supplied.
    if bool(member_id) == bool(staff_id):
        return Response(
            {"error": "Provide either a member ID or a staff ID, not both."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    mapping = BiometricEmployeeMapping.objects.filter(
        id=mapping_id,
        tenant=tenant,
    ).first()

    if mapping is None:
        return Response(
            {"error": "Biometric mapping not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    if member_id:
        person = Member.objects.filter(
            id=member_id,
            tenant=tenant,
        ).first()

        if person is None:
            return Response(
                {"error": "Member not found in this tenant"},
                status=status.HTTP_404_NOT_FOUND,
            )

        mapping.member = person
        mapping.staff = None

    else:
        person = Staffs.objects.filter(
            id=staff_id,
            tenant=tenant,
        ).first()

        if person is None:
            return Response(
                {"error": "Staff not found in this tenant"},
                status=status.HTTP_404_NOT_FOUND,
            )

        mapping.staff = person
        mapping.member = None

    try:
        with transaction.atomic():
            mapping.save()

    except IntegrityError:
        logger.exception(
            "Failed to link biometric mapping %s",
            mapping_id,
        )
        return Response(
            {
                "error": (
                    "Could not save the biometric mapping. "
                    "Check the database constraints and existing records."
                )
            },
            status=status.HTTP_409_CONFLICT,
        )

    return Response(
        BiometricEmployeeMappingSerializer(mapping).data,
        status=status.HTTP_200_OK,
    )


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def unlink_biometric_employee(request, mapping_id):
    tenant = get_tenant(request)

    if tenant is None:
        return Response(
            {"error": "User is not assigned to a tenant"},
            status=status.HTTP_403_FORBIDDEN,
        )

    mapping = BiometricEmployeeMapping.objects.filter(
        id=mapping_id,
        tenant=tenant,
    ).first()

    if mapping is None:
        return Response(
            {"error": "Biometric mapping not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    mapping.member = None
    mapping.staff = None
    mapping.save(update_fields=["member", "staff"])

    return Response(
        BiometricEmployeeMappingSerializer(mapping).data,
        status=status.HTTP_200_OK,
    )

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Attendance, BiometricEmployeeMapping
from .essl_service import call_essl

# KEEP your existing get_tenant import here.
# Example:
# from .utils import get_tenant

logger = logging.getLogger(__name__)

INDIA_TIMEZONE = ZoneInfo("Asia/Kolkata")
UTC_TIMEZONE = ZoneInfo("UTC")


def parse_essl_attendance_logs(raw_response):
    """
    Parse eSSL attendance logs.

    eSSL sends timestamps in Indian local time.
    Interpret the raw time as IST before saving it.
    Django stores aware datetimes in UTC when USE_TZ=True.
    """
    if raw_response is None:
        return []

    if isinstance(raw_response, list):
        return raw_response

    raw_text = str(raw_response).strip()

    if not raw_text:
        return []

    # Support XML SOAP responses.
    if raw_text.startswith("<"):
        try:
            root = ET.fromstring(raw_text)

            raw_text = " ".join(
                element.text.strip()
                for element in root.iter()
                if element.text and element.text.strip()
            )

        except ET.ParseError:
            logger.exception("Unable to parse eSSL SOAP XML.")
            return []

    parsed_logs = []

    for line in raw_text.replace("\r", "").split(";"):
        line = line.strip()

        if not line:
            continue

        parts = [part.strip() for part in line.split(",")]

        if len(parts) < 5:
            logger.warning("Skipping malformed eSSL record: %s", line)
            continue

        timestamp_text, employee_code, device_name, location, punch_type = (
            parts[:5]
        )

        try:
            naive_time = datetime.strptime(
                timestamp_text,
                "%Y-%m-%d %H:%M:%S",
            )

            # IMPORTANT: eSSL device time is interpreted as IST.
            punch_time = timezone.make_aware(
                naive_time,
                timezone=INDIA_TIMEZONE,
            )

        except ValueError:
            logger.warning(
                "Invalid eSSL timestamp: %s",
                timestamp_text,
            )
            continue

        if not employee_code:
            continue

        logger.info("eSSL raw timestamp: %s", timestamp_text)
        logger.info("Parsed IST timestamp: %s", punch_time.isoformat())
        logger.info(
            "Parsed UTC timestamp: %s",
            punch_time.astimezone(UTC_TIMEZONE).isoformat(),
        )

        parsed_logs.append({
            "employee_code": employee_code,
            "punch_time": punch_time,
            "punch_type": punch_type or "INOUT",
            "raw_data": {
                "device_name": device_name,
                "location": location,
                "original_record": line,
            },
        })

    return parsed_logs

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def sync_essl_attendance(request):
    """Sync attendance logs for all active attendance devices."""

    tenant = get_tenant(request)

    if tenant is None:
        return Response(
            {"detail": "Unable to determine the current tenant."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    date_value = request.data.get("date") or request.data.get("log_date")

    if date_value:
        try:
            log_date = datetime.strptime(
                str(date_value), "%Y-%m-%d"
            ).date()
        except ValueError:
            return Response(
                {"detail": "Invalid date. Use YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )
    else:
        log_date = timezone.localdate()

    username = getattr(settings, "ESSL_USERNAME", "")
    password = getattr(settings, "ESSL_PASSWORD", "")

    if not username or not password:
        return Response(
            {"detail": "eSSL credentials are not configured."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    devices = list(
        BiometricDevice.objects.filter(
            tenant=tenant,
            is_active=True,
            is_attendance_device=True,
        ).order_by("id")
    )

    if not devices:
        return Response(
            {
                "detail": (
                    "No active attendance devices are registered "
                    "for this tenant."
                )
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Group devices by location. The SOAP API accepts Location,
    # not the device serial number, in the current integration.
    devices_by_location = {}

    for device in devices:
        location = (
            device.location
            or request.data.get("location")
            or getattr(settings, "ESSL_LOCATION", "TCR")
        ).strip()

        devices_by_location.setdefault(location, []).append(device)

    results = []
    total_received = 0
    total_created = 0
    total_updated = 0
    total_skipped = 0
    failed_locations = []

    for location, location_devices in devices_by_location.items():
        try:
            raw_response = call_essl(
                "GetDeviceLogs",
                {
                    "UserName": username,
                    "Password": password,
                    "Location": location,
                    "LogDate": log_date.strftime("%Y-%m-%d"),
                },
            )

            parsed_logs = parse_essl_attendance_logs(raw_response)

            device_by_name = {
                device.name.strip().casefold(): device
                for device in location_devices
                if device.name.strip()
            }

            created_count = 0
            updated_count = 0
            skipped_count = 0
            matched_devices = set()

            with transaction.atomic():
                for log in parsed_logs:
                    employee_code = str(
                        log.get("employee_code", "")
                    ).strip()

                    punch_time = log.get("punch_time")
                    raw_data = log.get("raw_data") or {}

                    if not employee_code or not punch_time:
                        skipped_count += 1
                        continue

                    # The raw log contains the device name, e.g. uFace302.
                    log_device_name = str(
                        raw_data.get("device_name", "")
                    ).strip().casefold()

                    device = device_by_name.get(log_device_name)

                    # Do not guess which device produced a punch.
                    if device is None:
                        skipped_count += 1
                        logger.warning(
                            "Cannot identify attendance device: "
                            "tenant=%s location=%s device_name=%s",
                            tenant.pk,
                            location,
                            log_device_name,
                        )
                        continue

                    matched_devices.add(device.pk)

                    mapping = (
                        BiometricEmployeeMapping.objects.filter(
                            tenant=tenant,
                            essl_employee_code=employee_code,
                            is_active=True,
                        ).first()
                    )

                    original_record = raw_data.get("original_record")

                    attendance = Attendance.objects.filter(
                        tenant=tenant,
                        essl_employee_code=employee_code,
                        punch_time=punch_time,
                    ).first()

                    if attendance is None and original_record:
                        attendance = (
                            Attendance.objects.filter(
                                tenant=tenant,
                                essl_employee_code=employee_code,
                                raw_data__original_record=original_record,
                            )
                            .order_by("-punch_time")
                            .first()
                        )

                        if attendance is not None:
                            duplicate_exists = Attendance.objects.filter(
                                tenant=tenant,
                                essl_employee_code=employee_code,
                                punch_time=punch_time,
                            ).exclude(pk=attendance.pk).exists()

                            if duplicate_exists:
                                skipped_count += 1
                                continue

                    if attendance is not None:
                        attendance.punch_time = punch_time
                        attendance.biometric_mapping = mapping
                        attendance.punch_type = log.get(
                            "punch_type", "INOUT"
                        )
                        attendance.raw_data = raw_data
                        attendance.device = device

                        attendance.save(
                            update_fields=[
                                "punch_time",
                                "biometric_mapping",
                                "punch_type",
                                "raw_data",
                                "device",
                            ]
                        )
                        updated_count += 1

                    else:
                        Attendance.objects.create(
                            tenant=tenant,
                            essl_employee_code=employee_code,
                            punch_time=punch_time,
                            biometric_mapping=mapping,
                            device=device,
                            punch_type=log.get("punch_type", "INOUT"),
                            raw_data=raw_data,
                        )
                        created_count += 1

                # Update only devices whose logs were processed successfully.
                for device in location_devices:
                    if device.pk in matched_devices:
                        device.last_synced_at = timezone.now()
                        device.save(update_fields=["last_synced_at"])

            total_received += len(parsed_logs)
            total_created += created_count
            total_updated += updated_count
            total_skipped += skipped_count

            for device in location_devices:
                results.append({
                    "device_id": device.pk,
                    "device_name": device.name,
                    "serial_number": device.serial_number,
                    "location": location,
                    "status": (
                        "success"
                        if device.pk in matched_devices
                        else "no_matching_logs"
                    ),
                    "received": len(parsed_logs),
                    "created": created_count,
                    "updated": updated_count,
                    "skipped": skipped_count,
                })

        except Exception as exc:
            logger.exception(
                "Attendance sync failed for location %s, tenant %s",
                location,
                tenant.pk,
            )

            failed_locations.append(location)

            for device in location_devices:
                results.append({
                    "device_id": device.pk,
                    "device_name": device.name,
                    "serial_number": device.serial_number,
                    "location": location,
                    "status": "failed",
                    "error": str(exc),
                })

    has_failures = bool(failed_locations)

    response_data = {
        "message": (
            "Attendance sync completed with errors."
            if has_failures
            else "Attendance sync completed."
        ),
        "tenant_id": tenant.pk,
        "log_date": log_date.isoformat(),
        "received": total_received,
        "created": total_created,
        "updated": total_updated,
        "skipped": total_skipped,
        "failed_locations": failed_locations,
        "devices": results,
    }

    return Response(
        response_data,
        status=(
            status.HTTP_502_BAD_GATEWAY
            if has_failures
            else status.HTTP_200_OK
        ),
    )

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_attendance(request):
    """Return attendance records belonging to the current tenant."""

    tenant = get_tenant(request)

    if tenant is None:
        return Response(
            {"detail": "Unable to determine the current tenant."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    queryset = Attendance.objects.filter(
        tenant=tenant
    ).select_related(
        "biometric_mapping",
        "biometric_mapping__member",
        "biometric_mapping__staff",
    )

    employee_code = request.query_params.get(
        "employee_code", ""
    ).strip()

    if employee_code:
        queryset = queryset.filter(
            essl_employee_code=employee_code
        )

    month_value = request.query_params.get(
        "month", ""
    ).strip()

    if month_value:
        try:
            selected_month = datetime.strptime(
                month_value,
                "%Y-%m",
            ).date()

        except ValueError:
            return Response(
                {"detail": "Invalid month. Use YYYY-MM."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        start_of_month = timezone.make_aware(
            datetime(
                selected_month.year,
                selected_month.month,
                1,
            ),
            timezone=INDIA_TIMEZONE,
        )

        if selected_month.month == 12:
            next_month_date = datetime(
                selected_month.year + 1,
                1,
                1,
            )
        else:
            next_month_date = datetime(
                selected_month.year,
                selected_month.month + 1,
                1,
            )

        start_of_next_month = timezone.make_aware(
            next_month_date,
            timezone=INDIA_TIMEZONE,
        )

        queryset = queryset.filter(
            punch_time__gte=start_of_month,
            punch_time__lt=start_of_next_month,
        )

    date_value = request.query_params.get(
        "date", ""
    ).strip()

    if date_value:
        try:
            selected_date = datetime.strptime(
                date_value,
                "%Y-%m-%d",
            ).date()

        except ValueError:
            return Response(
                {"detail": "Invalid date. Use YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        start_of_day = timezone.make_aware(
            datetime.combine(
                selected_date,
                datetime.min.time(),
            ),
            timezone=INDIA_TIMEZONE,
        )

        start_of_next_day = timezone.make_aware(
            datetime.combine(
                selected_date + timedelta(days=1),
                datetime.min.time(),
            ),
            timezone=INDIA_TIMEZONE,
        )

        queryset = queryset.filter(
            punch_time__gte=start_of_day,
            punch_time__lt=start_of_next_day,
        )

    search = request.query_params.get(
        "search", ""
    ).strip()

    if search:
        queryset = queryset.filter(
            Q(essl_employee_code__icontains=search)
            | Q(
                biometric_mapping__essl_employee_name__icontains=search
            )
        )

    records = queryset.order_by("-punch_time")

    results = []

    for record in records:
        mapping = record.biometric_mapping

        results.append({
            "id": record.pk,
            "employee_code": record.essl_employee_code,
            "employee_name": (
                mapping.essl_employee_name
                if mapping else None
            ),
            "member_id": (
                mapping.member_id
                if mapping and mapping.member_id
                else None
            ),
            "staff_id": (
                mapping.staff_id
                if mapping and mapping.staff_id
                else None
            ),
            "punch_time": (
                record.punch_time.isoformat()
                if record.punch_time
                else None
            ),
            "punch_type": record.punch_type,
            "raw_data": record.raw_data or {},
        })

    return Response(
        {
            "count": len(results),
            "results": results,
        },
        status=status.HTTP_200_OK,
    )