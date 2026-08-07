from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Branch, Enquiry, Expense, Payment, Product, Sales_product, Member,Expense,Income,MemberPause
import json
from datetime import datetime
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate


@api_view(["POST"])
@permission_classes([AllowAny])
def admin_login(request):
    username = request.data.get("username")
    password = request.data.get("password")

    if not username or not password:
        return JsonResponse(
            {"error": "Username and password are required"},status=404)

    user = authenticate(username=username, password=password)

    if user is None:
        return JsonResponse(
            {"error": "Invalid username or password"},status=401)

    refresh = RefreshToken.for_user(user)

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
            }},status=200)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def change_password(request):
    user = request.user
    current_password = request.data.get("current_password")
    new_password = request.data.get("new_password")
    confirm_password = request.data.get("confirm_password")

    if not current_password or not new_password or not confirm_password:
        return JsonResponse({"error": "All fields are required"},status=400)

    if not user.check_password(current_password):
        return JsonResponse({"error": "Current password is incorrect"},status=400)

    if new_password != confirm_password:
        return JsonResponse({"error": "New password and confirm password do not match"},status=400)

    if len(new_password) < 6:
        return JsonResponse({"error": "New password must be at least 6 characters long"},status=400)

    user.set_password(new_password)
    user.save()

    return JsonResponse({"message": "Password changed successfully"},status=200)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_profile_view(request):
    user = request.user

    return JsonResponse(
        {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": f"{user.first_name} {user.last_name}".strip() or user.username,
            "is_staff": user.is_staff,
            "is_superuser": user.is_superuser,
        }
    )


#.......................... MEMBERS

@csrf_exempt
def create_member(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        # Member ID
        last_member = Member.objects.order_by("-id").first()
        next_id = f"{int(last_member.id) + 1:04d}" if last_member else "0001"

        # Inputs
        plan_id = request.POST.get("plan")
        branch_id = request.POST.get("branch")
        join_date_str = request.POST.get("join_date")
        phone = request.POST.get("phone", "").strip()
        email = request.POST.get("email", "").strip().lower()

        if email and Member.objects.filter(email=email).exists():
            return JsonResponse(
                {"error": "Email already exists"},
                status=400
            )        

        if not plan_id:
            return JsonResponse({"error": "Plan is required"}, status=400)

        if not branch_id:
            return JsonResponse({"error": "Branch is required"}, status=400)

        if not join_date_str:
            return JsonResponse({"error": "Join date is required"}, status=400)

        # Phone validation
        if not (phone.isdigit() and len(phone) == 10):
            return JsonResponse(
                {"error": "Enter a valid 10-digit mobile number"},
                status=400
            )

        # duplicate phone number
        if Member.objects.filter(phone=phone).exists():  
            return JsonResponse(
                {"error": "Mobile number already exists"},
                status=400
            )        

        # Get selected plan from DB
        try:
            plan = Plan.objects.get(id=plan_id)
        except Plan.DoesNotExist:
            return JsonResponse({"error": "Invalid plan selected"}, status=400)

        try:
            branch = Branch.objects.get(id=branch_id)
        except Branch.DoesNotExist:
            return JsonResponse({"error": "Invalid Branch selected"}, status=400)        

        # Parse join date
        try:
            join_date = datetime.strptime(join_date_str, "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse(
                {"error": "Invalid join date"},
                status=400
            )

        # Expiry from plan duration
        duration = int(plan.duration or 0)
        expiry_date = join_date + timedelta(days=duration)

        # BMI calculation
        try:
            weight = float(request.POST.get("weight") or 0)
            height = float(request.POST.get("height") or 0)
        except ValueError:
            return JsonResponse({"error": "Invalid height or weight"}, status=400)

        bmi = None
        if height > 0 and weight > 0:
            height_m = height / 100
            bmi = round(weight / (height_m * height_m), 2)

        # Payment
        try:
            paid_amount = float(request.POST.get("paid_amount") or 0)
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

        plan_amount = float(plan.price or 0)

        if paid_amount > plan_amount:
            return JsonResponse(
                {"error": "Paid amount cannot exceed plan price"},
                status=400
            )

        due_amount = plan_amount - paid_amount

        plan_amount = float(plan.price or 0)
        due_amount = max(plan_amount - paid_amount, 0)

        photo = request.FILES.get("photo")

        member = Member.objects.create(
            id=next_id,
            name=request.POST.get("name"),
            phone=phone,
            email=email,
            plan=plan.name,   # if your Member.plan field is CharField
            branch=branch.name,
            join_date=join_date,
            photo=photo,
            height=height,
            weight=weight,
            bmi=bmi,
            age=request.POST.get("age"),
            blood_group=request.POST.get("blood_group"),
            location=request.POST.get("location"),
            adhaar_number=request.POST.get("adhaar_number"),
            gender=request.POST.get("gender"),
            paid_amount=paid_amount,
            due_amount=due_amount,
            expiry_date=expiry_date,
            status="Active",
        )

        return JsonResponse({
            "status": True,
            "message": "Member created successfully",
            "data": {
                "id": member.id,
                "name": member.name,
                "plan": member.plan,
                "branch": member.branch,
                "status": member.status,
                "expiry_date": member.expiry_date,
                "bmi": member.bmi,
                "due": member.due_amount,
            }
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    
    

from datetime import date
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

def auto_resume_member(member, today):

    if member.is_paused and member.pause_expiry_date:

        if today >= member.pause_expiry_date:

            active_pause = MemberPause.objects.filter(
                member=member,
                end_date__isnull=True
            ).first()

            if active_pause:

                paused_days = (
                    today - active_pause.start_date
                ).days

                active_pause.end_date = today
                active_pause.paused_days = paused_days
                active_pause.save()

                if member.expiry_date:
                    member.expiry_date += timedelta(
                        days=paused_days
                    )

            member.is_paused = False
            member.pause_start_date = None
            member.pause_expiry_date = None
            member.status = "Active"

            member.save()

@csrf_exempt
def get_members(request):

    if request.method == "GET":

        today = date.today()

        members = Member.objects.all().order_by("-id")

        data = []

        for member in members:


            # AUTO RESUME CHECK
            auto_resume_member(
                member,
                today
            )


            # STATUS UPDATE

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


            member.save()


            # MONTH PAUSE DATA

            month_start = today.replace(day=1)

            if today.month == 12:

                next_month = today.replace(
                    year=today.year + 1,
                    month=1,
                    day=1
                )

            else:

                next_month = today.replace(
                    month=today.month + 1,
                    day=1
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

                "plan": member.plan,
                "branch": member.branch,

                "join_date": member.join_date,
                "expiry_date": member.expiry_date,

                "paid_amount": member.paid_amount,
                "due_amount": member.due_amount,

                "status": member.status,

                "photo": (
                    member.photo.url
                    if member.photo else None
                ),

                "pause_start_date": member.pause_start_date,
                "pause_expiry_date": member.pause_expiry_date,

                "is_paused": member.is_paused,

                "pause_days_used": used_days,
                "pause_days_remaining": remaining_days,
                "pause_count": pause_count,

            })


        return JsonResponse(
            data,
            safe=False
        )

    return JsonResponse(
        {"error":"Invalid request"},
        status=405
    )
@csrf_exempt
def get_member(request, member_id):

    if request.method == "GET":

        try:

            member = Member.objects.get(
                id=member_id
            )

            today = date.today()


            # AUTO RESUME CHECK

            auto_resume_member(
                member,
                today
            )


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


            member.save()


            month_start = today.replace(day=1)


            if today.month == 12:

                next_month = today.replace(
                    year=today.year+1,
                    month=1,
                    day=1
                )

            else:

                next_month = today.replace(
                    month=today.month+1,
                    day=1
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
                15-used_days,
                0
            )


            pause_count = pauses.count()



            data = {

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

                "plan": member.plan,
                "branch": member.branch,

                "join_date": member.join_date,
                "expiry_date": member.expiry_date,

                "status": member.status,

                "paid_amount": member.paid_amount,
                "due_amount": member.due_amount,

                "photo": (
                    member.photo.url
                    if member.photo else None
                ),

                "pause_start_date": member.pause_start_date,
                "pause_expiry_date": member.pause_expiry_date,

                "is_paused": member.is_paused,


                "pause_days_used": used_days,
                "pause_days_remaining": remaining_days,
                "pause_count": pause_count,

            }


            return JsonResponse(data)


        except Member.DoesNotExist:

            return JsonResponse(
                {"error":"Member not found"},
                status=404
            )


    return JsonResponse(
        {"error":"Invalid request"},
        status=405
    )

from datetime import datetime, timedelta
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def update_member(request, member_id):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        member = Member.objects.get(id=member_id)
    except Member.DoesNotExist:
        return JsonResponse({"error": "Member not found"}, status=404)

    # Plan duration map
    plan_days = {
        "Silver": 30,
        "Gold": 60,
        "Premium": 90,
        "Platinum": 180,
        "Diamond": 365,
    }

    # -----------------------
    # BASIC FIELDS
    # -----------------------
    member.name = request.POST.get("name")
    member.phone = request.POST.get("phone")
    member.email = request.POST.get("email")
    member.height = request.POST.get("height")
    member.weight = request.POST.get("weight")
    member.age = request.POST.get("age")
    member.blood_group = request.POST.get("blood_group")
    member.location = request.POST.get("location")
    member.adhaar_number = request.POST.get("adhaar_number")
    member.gender = request.POST.get("gender")

    if request.POST.get("status"):
        member.status = request.POST.get("status")

    if request.FILES.get("photo"):
        member.photo = request.FILES.get("photo")

    # -----------------------
    # PLAN + JOIN DATE LOGIC
    # -----------------------
    plan = request.POST.get("plan")
    join_date_str = request.POST.get("join_date")

    # convert join_date safely
    if join_date_str:
        try:
            join_date = datetime.strptime(join_date_str, "%Y-%m-%d").date()
            member.join_date = join_date
        except ValueError:
            return JsonResponse({"error": "Invalid join_date format"}, status=400)

    if plan:
        member.plan = plan

    # -----------------------
    # EXPIRY CALCULATION (FIXED)
    # -----------------------
    if member.plan and member.join_date:
        days = plan_days.get(member.plan, 0)

        # IMPORTANT:
        # If member already has paused extensions, keep them
        paused_extension = 0

        if hasattr(member, "pause_start_date") and member.pause_start_date:
            # optional safety (not strictly needed here)
            paused_extension = 0

        member.expiry_date = member.join_date + timedelta(days=days + paused_extension)

    # -----------------------
    # SAVE
    # -----------------------
    member.save()

    return JsonResponse({
        "message": "Member updated successfully",
        "id": member.id,
        "expiry_date":member.expiry_date
    })


@csrf_exempt
def delete_member(request, member_id):
    if request.method == "DELETE":
        try:
            member = Member.objects.get(id=member_id)
            member.delete()

            return JsonResponse({"message": "Member deleted successfully"})

        except Member.DoesNotExist:
            return JsonResponse({"error": "Member not found"},status=404)


from .models import Plan

#.................................. PLANS 


@csrf_exempt
def create_plan(request):
    if request.method == "POST":

        plan = Plan.objects.create(
            name=request.POST.get("name"),
            duration=request.POST.get("duration"),
            price=request.POST.get("price")
        )

        return JsonResponse({"message": "success"})

    return JsonResponse({"error": "Invalid request method"}, status=405)

@csrf_exempt
def get_plans(request):
    if request.method == "GET":
        plans = list(Plan.objects.order_by('id').values())
        return JsonResponse(plans, safe=False)



@csrf_exempt
def update_plan(request, plan_id):
    if request.method == "POST":

        try:
            plan = Plan.objects.get(id=plan_id)
        except Plan.DoesNotExist:
            return JsonResponse(
                {"error": "Plan not found"},
                status=404
            )

        plan.name = request.POST.get("name")
        plan.duration = request.POST.get("duration")
        plan.price = request.POST.get("price")
        
        plan.save()

        return JsonResponse({"message":"Updation success"})

    return JsonResponse({"error": "Invalid request method"}, status=405)


@csrf_exempt
def delete_plan(request, plan_id):
    if request.method == "DELETE":
        try:
            plan = Plan.objects.get(id=plan_id)
            plan.delete()

            return JsonResponse({"message": "Plan deleted successfully"})

        except Plan.DoesNotExist:
            return JsonResponse({"error": "Plan not found"},status=404)
        


@csrf_exempt
def create_branch(request):
    if request.method == "POST":

        branch = Branch.objects.create(
            name=request.POST.get("name"),
            location=request.POST.get("location"),
            manager_name=request.POST.get("manager_name"),
            phone=request.POST.get("phone"),
            capacity=request.POST.get("capacity")
        )

        return JsonResponse({"message": "success"})


@csrf_exempt
def get_branches(request):
    if request.method == "GET":
        branches = list(Branch.objects.order_by('id').values())
        return JsonResponse(branches, safe=False)



@csrf_exempt
def get_branch_members(request, branch_id):
    if request.method != "GET":
        return JsonResponse({"error": "Method not allowed"},status=405)

    try:
        branch = Branch.objects.get(id=branch_id)

        # Only active members
        members = Member.objects.filter(branch=branch.name,status="Active"
)

        member_data = []
        for member in members:
            member_data.append({
                "id": member.id,
                "name": member.name,
                "phone": member.phone,
                "email": member.email,
                "plan": member.plan,
            })

        return JsonResponse({
            "branch": branch.name,
            "customers": member_data
        })

    except Branch.DoesNotExist:
        return JsonResponse({"error": "Branch not found"},status=404)

    except Exception as e:
        return JsonResponse({"error": str(e)},status=500)



@csrf_exempt
def update_branch(request, branch_id):
    if request.method == "POST":
        try:
            branch = Branch.objects.get(id=branch_id)
        except Branch.DoesNotExist:
            return JsonResponse({"message": "Branch not found"},status=404)

        branch.name = request.POST.get("name")
        branch.location = request.POST.get("location")
        branch.manager_name = request.POST.get("manager_name")
        branch.phone = request.POST.get("phone")
        branch.capacity = request.POST.get("capacity")
        branch.save()

        return JsonResponse({"message": "Branch updated successfully"})



@csrf_exempt
def delete_branch(request, branch_id):
    if request.method == "DELETE":
        try:
            branch = Branch.objects.get(id=branch_id)
            branch.delete()

            return JsonResponse({"message": "Branch deleted successfully"})

        except Branch.DoesNotExist:
            return JsonResponse({"error": "Branch not found"},status=404)
            

from django.db.models import Sum
from datetime import date, timedelta


def calculate_growth(current, previous):
    if previous == 0:
        return 100 if current > 0 else 0

    return round(((current - previous) / previous) * 100, 2)

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

# Import your models
from .models import Member, Income, Expense, Sales_product

from datetime import date, datetime, timedelta
import calendar

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


    # ==========================
    # DAILY
    # ==========================

    if period == "daily":

        start_date = today
        end_date = today


    # ==========================
    # WEEKLY
    # Monday -> Today
    # ==========================

    elif period == "weekly":

        start_date = today - timedelta(
            days=today.weekday()
        )

        end_date = today


    # ==========================
    # MONTHLY
    # 1st -> Today
    # ==========================

    elif period == "monthly":

        start_date = today.replace(
            day=1
        )

        end_date = today


    # ==========================
    # YEARLY
    # Jan 1 -> Today
    # ==========================

    elif period == "yearly":

        start_date = today.replace(
            month=1,
            day=1
        )

        end_date = today


    else:

        return None, None


    return start_date, end_date


@csrf_exempt
def get_dashboard_stats(request):

    if request.method != "GET":
        return JsonResponse(
            {
                "error": "Invalid request method"
            },
            status=405
        )


    # =====================================================
    # PERIOD FILTER
    # =====================================================

    period = request.GET.get(
        "period",
        "daily"
    ).lower()

    date_str = request.GET.get(
        "date"
    )


    if date_str:

        try:
            today = datetime.strptime(
                date_str,
                "%Y-%m-%d"
            ).date()

        except ValueError:

            return JsonResponse(
                {
                    "error": "Invalid date format. Use YYYY-MM-DD"
                },
                status=400
            )

    else:

        today = date.today()



    start_date, end_date = get_period_dates(
        period,
        today
    )


    if start_date is None:

        return JsonResponse(
            {
                "error": "Invalid period. Use daily, weekly, monthly or yearly."
            },
            status=400
        )



    # =====================================================
    # LAST MONTH CALCULATION
    # =====================================================

    if today.month == 1:

        last_month = 12
        last_year = today.year - 1

    else:

        last_month = today.month - 1
        last_year = today.year



    # =====================================================
    # MEMBER STATISTICS
    # =====================================================


    total_members = Member.objects.count()


    active_members = Member.objects.filter(
        status="Active"
    ).count()


    blocked_members = Member.objects.filter(
        status="Blocked"
    ).count()


    expired_members = Member.objects.filter(
        status="Expired"
    ).count()


    paused_members = Member.objects.filter(
        is_paused=True
    ).count()


    pending_payments = Member.objects.filter(
        due_amount__gt=0
    ).count()



    # =====================================================
    # UPCOMING EXPIRIES
    # =====================================================


    next_week = today + timedelta(
        days=7
    )


    expiries = Member.objects.filter(
        status="Active",
        expiry_date__gte=today,
        expiry_date__lte=next_week
    ).order_by(
        "expiry_date"
    )


    upcoming_expiries_list = [

        {
            "name": member.name,
            "phone": member.phone,
            "expiry_date": member.expiry_date,
            "due_amount": member.due_amount,
        }

        for member in expiries

    ]



    # =====================================================
    # RECENT REGISTRATIONS
    # =====================================================


    recent = Member.objects.order_by(
        "-id"
    )[:5]


    recent_registrations = [

        {
            "name": member.name,
            "phone": member.phone,
            "email": member.email,
            "plan": member.plan,
            "join_date": member.join_date,
        }

        for member in recent

    ]



    # =====================================================
    # TOTAL INCOME
    # =====================================================


    total_membership_income = (

        Income.objects.aggregate(
            total=Sum("amount")
        )["total"]

        or Decimal("0")

    )


    total_product_income = (

        Sales_product.objects.aggregate(
            total=Sum("total_amount")
        )["total"]

        or Decimal("0")

    )


    total_income = (

        total_membership_income

        +

        total_product_income

    )



    # =====================================================
    # SELECTED PERIOD INCOME
    # =====================================================


    period_membership_income = (

        Income.objects.filter(

            date__date__gte=start_date,

            date__date__lte=end_date

        ).aggregate(
            total=Sum("amount")
        )["total"]

        or Decimal("0")

    )


    period_product_income = (

        Sales_product.objects.filter(

            sold_at__date__gte=start_date,

            sold_at__date__lte=end_date

        ).aggregate(
            total=Sum("total_amount")
        )["total"]

        or Decimal("0")

    )


    period_income = (

        period_membership_income

        +

        period_product_income

    )



    # =====================================================
    # TODAY INCOME
    # =====================================================


    today_membership_income = (

        Income.objects.filter(

            date__date=today

        ).aggregate(
            total=Sum("amount")
        )["total"]

        or Decimal("0")

    )


    today_product_income = (

        Sales_product.objects.filter(

            sold_at__date=today

        ).aggregate(
            total=Sum("total_amount")
        )["total"]

        or Decimal("0")

    )


    today_income = (

        today_membership_income

        +

        today_product_income

    )

        # =====================================================
    # MONTHLY INCOME
    # =====================================================

    monthly_membership_income = (

        Income.objects.filter(

            date__year=today.year,

            date__month=today.month

        ).aggregate(
            total=Sum("amount")
        )["total"]

        or Decimal("0")

    )


    monthly_product_income = (

        Sales_product.objects.filter(

            sold_at__year=today.year,

            sold_at__month=today.month

        ).aggregate(
            total=Sum("total_amount")
        )["total"]

        or Decimal("0")

    )


    monthly_income = (

        monthly_membership_income

        +

        monthly_product_income

    )



    # =====================================================
    # YEARLY INCOME
    # =====================================================

    yearly_membership_income = (

        Income.objects.filter(

            date__year=today.year

        ).aggregate(
            total=Sum("amount")
        )["total"]

        or Decimal("0")

    )


    yearly_product_income = (

        Sales_product.objects.filter(

            sold_at__year=today.year

        ).aggregate(
            total=Sum("total_amount")
        )["total"]

        or Decimal("0")

    )


    yearly_income = (

        yearly_membership_income

        +

        yearly_product_income

    )



    # =====================================================
    # LAST MONTH INCOME
    # =====================================================


    last_month_membership_income = (

        Income.objects.filter(

            date__year=last_year,

            date__month=last_month

        ).aggregate(
            total=Sum("amount")
        )["total"]

        or Decimal("0")

    )


    last_month_product_income = (

        Sales_product.objects.filter(

            sold_at__year=last_year,

            sold_at__month=last_month

        ).aggregate(
            total=Sum("total_amount")
        )["total"]

        or Decimal("0")

    )


    last_month_income = (

        last_month_membership_income

        +

        last_month_product_income

    )



    # =====================================================
    # SALES
    # =====================================================


    total_sales = (

        Sales_product.objects.aggregate(
            total=Sum("total_amount")
        )["total"]

        or Decimal("0")

    )


    period_sales = (

        Sales_product.objects.filter(

            sold_at__date__gte=start_date,

            sold_at__date__lte=end_date

        ).aggregate(
            total=Sum("total_amount")
        )["total"]

        or Decimal("0")

    )


    today_sales = (

        Sales_product.objects.filter(

            sold_at__date=today

        ).aggregate(
            total=Sum("total_amount")
        )["total"]

        or Decimal("0")

    )


    monthly_sales = (

        Sales_product.objects.filter(

            sold_at__year=today.year,

            sold_at__month=today.month

        ).aggregate(
            total=Sum("total_amount")
        )["total"]

        or Decimal("0")

    )


    last_month_sales = (

        Sales_product.objects.filter(

            sold_at__year=last_year,

            sold_at__month=last_month

        ).aggregate(
            total=Sum("total_amount")
        )["total"]

        or Decimal("0")

    )



    # =====================================================
    # EXPENSE
    # =====================================================


    total_expense = (

        Expense.objects.aggregate(
            total=Sum("amount")
        )["total"]

        or Decimal("0")

    )


    period_expense = (

        Expense.objects.filter(

            date__gte=start_date,

            date__lte=end_date

        ).aggregate(
            total=Sum("amount")
        )["total"]

        or Decimal("0")

    )


    today_expense = (

        Expense.objects.filter(

            date=today

        ).aggregate(
            total=Sum("amount")
        )["total"]

        or Decimal("0")

    )


    monthly_expense = (

        Expense.objects.filter(

            date__year=today.year,

            date__month=today.month

        ).aggregate(
            total=Sum("amount")
        )["total"]

        or Decimal("0")

    )


    last_month_expense = (

        Expense.objects.filter(

            date__year=last_year,

            date__month=last_month

        ).aggregate(
            total=Sum("amount")
        )["total"]

        or Decimal("0")

    )



    # =====================================================
    # PROFIT / LOSS
    # =====================================================


    period_profit = period_income - period_expense

    period_loss = period_expense - period_income


    today_profit = today_income - today_expense

    today_loss = today_expense - today_income


    monthly_profit = monthly_income - monthly_expense

    monthly_loss = monthly_expense - monthly_income


    total_profit = total_income - total_expense

    total_loss = total_expense - total_income



    values = [

        "period_profit",
        "period_loss",
        "today_profit",
        "today_loss",
        "monthly_profit",
        "monthly_loss",
        "total_profit",
        "total_loss"

    ]


    for value in values:

        if locals()[value] < 0:

            locals()[value] = Decimal("0")



    # =====================================================
    # CATEGORY INCOME
    # =====================================================


    membership_income = (

        Income.objects.filter(
            category="membership"
        ).aggregate(
            total=Sum("amount")
        )["total"]

        or Decimal("0")

    )


    product_income = (

        Sales_product.objects.aggregate(
            total=Sum("total_amount")
        )["total"]

        or Decimal("0")

    )


    admission_income = (

        Income.objects.filter(
            category="other"
        ).aggregate(
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


    profit_growth = calculate_growth(
        monthly_profit,
        max(last_month_income - last_month_expense, 0)
    )


    sales_growth = calculate_growth(
        monthly_sales,
        last_month_sales
    )

    # =====================================================
    # YEARLY SALES
    # =====================================================

    yearly_sales = (
        Sales_product.objects.filter(
            sold_at__year=today.year
        ).aggregate(
            total=Sum("total_amount")
        )["total"]
        or Decimal("0")
    )



    # =====================================================
    # YEARLY EXPENSE
    # =====================================================

    yearly_expense = (
        Expense.objects.filter(
            date__year=today.year
        ).aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0")
    )



    # =====================================================
    # YEARLY PROFIT / LOSS
    # =====================================================

    yearly_profit = (
        yearly_income - yearly_expense
    )


    yearly_loss = (
        yearly_expense - yearly_income
    )


    if yearly_profit < 0:
        yearly_profit = Decimal("0")


    if yearly_loss < 0:
        yearly_loss = Decimal("0")



    # =====================================================
    # RESPONSE
    # =====================================================


    return JsonResponse({

        "period": period,

        "start_date": start_date,

        "end_date": end_date,


        "total_members": total_members,

        "active_members": active_members,

        "blocked_members": blocked_members,

        "expired_members": expired_members,

        "paused_members": paused_members,

        "pending_payments": pending_payments,


        "total_income": period_income,

        "total_sales": period_sales,

        "total_expense": period_expense,

        "total_profit": period_profit,

        "period_loss": period_loss,


        "today_income": today_income,

        "today_sales": today_sales,

        "today_expense": today_expense,

        "today_profit": today_profit,

        "today_loss": today_loss,


        "monthly_income": monthly_income,

        "monthly_sales": monthly_sales,

        "monthly_expense": monthly_expense,

        "monthly_profit": monthly_profit,

        "monthly_loss": monthly_loss,

        "yearly_income": yearly_income,

        "yearly_sales": yearly_sales,

        "yearly_expense": yearly_expense,

        "yearly_profit": yearly_profit,

        "yearly_loss": yearly_loss,


        "all_time_income": total_income,

        "all_time_sales": total_sales,

        "all_time_expense": total_expense,

        "all_time_profit": total_profit,

        "total_loss": total_loss,


        "membership_income": membership_income,

        "product_income": product_income,

        "admission_income": admission_income,


        "sales_growth": sales_growth,

        "revenue_growth": revenue_growth,

        "expense_growth": expense_growth,

        "profit_growth": profit_growth,


        "upcoming_expiries": len(
            upcoming_expiries_list
        ),

        "upcoming_expiries_list": upcoming_expiries_list,


        "recent_registrations": recent_registrations,

    })


def get_payments(request):
    data = []

    for payment in Payment.objects.select_related('member').all():
        member = payment.member

        total_paid = Payment.objects.filter(member=member).aggregate(
            total=Sum('amount')
        )['total'] or 0

        plan_fee = member.plan if member.plan else 0
        due_amount = plan_fee - total_paid
        if due_amount < 0:
            due_amount = 0

        data.append({
            "member_name": member.name,
            # "phone": member.phone,
            # "payment_id": payment.id,
            "amount_paid": payment.amount,
            "total_paid": total_paid,
            "due_amount": due_amount,
        })

    return JsonResponse(data, safe=False)



@csrf_exempt
def renew_member(request, member_id):
    if request.method != "POST":
        return JsonResponse({"message": "Invalid request"}, status=405)

    try:
        member = Member.objects.get(id=member_id)
    except Member.DoesNotExist:
        return JsonResponse({"message": "Member not found"}, status=404)

    plan_name = request.POST.get("plan")

    if not plan_name:
        return JsonResponse({"message": "Plan is required"}, status=400)

    try:
        plan = Plan.objects.get(name=plan_name)
    except Plan.DoesNotExist:
        return JsonResponse({"message": "Invalid plan"}, status=400)

    duration = plan.duration   # use your actual field name here

    today = date.today()

    # if current membership is still active, extend from current expiry
    if member.expiry_date and member.expiry_date >= today:
        member.expiry_date = member.expiry_date + timedelta(days=duration)
    else:
        # if expired / blocked, start from today
        member.expiry_date = today + timedelta(days=duration)

    member.plan = plan.name
    member.status = "Active"
    member.is_paused = False   # optional, useful if renewed member was paused/blocked
    member.save()

    return JsonResponse({
        "message": "Plan renewed successfully",
        "member_id": member.id,
        "member_name": member.name,
        "plan": member.plan,
        "new_expiry_date": member.expiry_date,
        "status": member.status,
    })



@csrf_exempt
def add_expense(request):
    if request.method == "POST":

        Expense.objects.create(
            title=request.POST.get("title"),
            category=request.POST.get("category"),
            amount=request.POST.get("amount"),
            date=request.POST.get("date"),
            description=request.POST.get("description", "")
        )

        return JsonResponse({"message": "Expense added successfully"})
    


@csrf_exempt
def view_expenses(request):

        expenses = list(Expense.objects.all().values())
        return JsonResponse({"expenses": expenses})

@csrf_exempt
def get_blocked_members(request):
    if request.method == "GET":
        members = Member.objects.filter(status="Blocked")

        data = []

        for member in members:
            data.append({
                "id": member.id,
                "name": member.name,
                "phone": member.phone,
                "plan":member.plan,
                "join_date":member.join_date,
                "expiry_date":member.expiry_date,
                "status": member.status,
                "photo": member.photo.url if member.photo else None,
            })

        return JsonResponse(data, safe=False)
    

@csrf_exempt
def send_whatsapp(request, member_id):
    member = Member.objects.get(id=member_id)

    return JsonResponse({
        "id": member.id,
        "name": member.name,
        "phone": member.phone,
        "due_amount": member.due_amount,
        "expiry_date":member.expiry_date
    })


def expiring_soon_members(request):
    today = date.today()

    start_date = today - timedelta(days=5)   # 5 days before today
    end_date = today + timedelta(days=5)       # 5 days after today

    members = Member.objects.filter(
        status="Active",
        expiry_date__gte=start_date,
        expiry_date__lte=end_date
    ).order_by("expiry_date")

    data = [
        {
            "id": m.id,
            "name": m.name,
            "phone": m.phone,
            "expiry_date": m.expiry_date,
            "due_amount": m.due_amount,
            "days_left": (m.expiry_date - today).days,
        }
        for m in members
    ]

    return JsonResponse(data, safe=False)



@csrf_exempt
def expired_members(request):
    today = date.today()

    members = Member.objects.filter(
        expiry_date__lt=today
    ).exclude(
        status__in=["Paused", "Blocked"]
    ).order_by("-expiry_date")

    data = []
    for member in members:
        data.append({
            "id": member.id,
            "name": member.name,
            "phone": member.phone,
            # "plan": member.plan.name if member.plan else None,
            "expiry_date": member.expiry_date,
            "status": member.status,
            "due_amount": member.due_amount,
        })

    return JsonResponse({"message": data}, safe=False)

import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Product


@csrf_exempt
def create_product(request):
    if request.method == "POST":
        product = Product.objects.create(
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
                "id": product.id,
            },
            status=201,
        )

    return JsonResponse({"error": "Only POST method allowed"}, status=405)


# READ
def get_products(request):
    products = Product.objects.all().order_by("id")
    data = []

    for product in products:
        data.append({
            "id": product.id,
            "name": product.name,
            "description": product.description,
            "price": product.price,
            "stock": product.stock,
            "category": product.category,
            "image": product.image.url if product.image else None,
        })

    return JsonResponse(data, safe=False)

# UPDATE

@csrf_exempt
def update_product(request, product_id):
    if request.method == "POST":
        try:
            product = Product.objects.get(id=product_id)

            product.name = request.POST.get("name", product.name)
            product.description = request.POST.get("description", product.description)
            product.price = request.POST.get("price", product.price)
            product.stock = request.POST.get("stock", product.stock)
            product.category = request.POST.get("category", product.category)

            # Update image only if a new one is uploaded
            if request.FILES.get("image"):
                product.image = request.FILES.get("image")

            product.save()

            return JsonResponse({"message": "Updated"}, status=200)

        except Product.DoesNotExist:
            return JsonResponse({"error": "Product not found"}, status=404)

    return JsonResponse({"error": "Only POST method allowed"}, status=405)


# DELETE

@csrf_exempt
def delete_product(request, product_id):
    if request.method != "DELETE":
        return JsonResponse(
            {"error": "Method not allowed"},
            status=405
        )
    try:
        product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
        return JsonResponse(
            {"error": "Product not found"},
            status=404
        )

    product.delete()

    return JsonResponse(
        {"message": "Deleted successfully"},
        status=200
    )


@csrf_exempt
def sell_product(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Invalid request method"})

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "message": "Invalid JSON"})

    product_id = data.get("product_id")
    member_id = data.get("member_id")
    quantity = int(data.get("quantity", 0))
    payment_method = data.get("payment_method", "cash")

    if not product_id or not member_id:
        return JsonResponse({"success": False, "message": "Missing data"})

    if quantity <= 0:
        return JsonResponse({"success": False, "message": "Invalid quantity"})

    try:
        member = Member.objects.get(id=member_id)
    except Member.DoesNotExist:
        return JsonResponse({"success": False, "message": "Member not found"})

    try:
        product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
        return JsonResponse({"success": False, "message": "Product not found"})

    if quantity > product.stock:
        return JsonResponse({"success": False, "message": "Insufficient stock"})

    unit_price = product.price
    total_amount = unit_price * quantity

    sale = Sales_product.objects.create(
        member=member,
        product=product,
        quantity=quantity,
        unit_price=unit_price,
        total_amount=total_amount,
        payment_method=payment_method
    )

    product.stock -= quantity
    product.save()

    return JsonResponse({
        "success": True,
        "message": "Sale completed",
        "sale_id": sale.id
    })

@csrf_exempt
def sales_list(request):

    if request.method != "GET":
        return JsonResponse(
            {"error": "GET request only"},
            status=405
        )

    period = request.GET.get(
        "period",
        "daily"
    ).lower()

    selected_date = request.GET.get(
        "date"
    )


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
        .select_related(
            "product",
            "member"
        )
        .filter(
            sold_at__date__gte=start_date,
            sold_at__date__lte=end_date
        )
        .order_by("-sold_at")
    )

    data = []

    for sale in sales:

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

            "unit_price": float(
                sale.unit_price
            ),

            "total_amount": float(
                sale.total_amount
            ),

            "sold_at": sale.sold_at.strftime(
                "%d-%m-%Y %H:%M"
            ),
        })

    return JsonResponse({
        "success": True,
        "period": period,
        "start_date": start_date,
        "end_date": end_date,
        "sales": data
    })


@csrf_exempt
def validate_member(request, member_id):
    try:
        member = Member.objects.get(id=member_id)

        return JsonResponse({
            "exists": True,
            "member_name": member.name
        })

    except Member.DoesNotExist:
        return JsonResponse({
            "exists": False,
            "message": "Not enough stock available"
        })

from django.shortcuts import get_object_or_404

@csrf_exempt
def one_sale(request, sale_id):
    sale = get_object_or_404(Sales_product, id=sale_id)

    return JsonResponse({
        "id": sale.id,
        "member_id": sale.member_id,
        "member_name": sale.member.name,
        "product": getattr(sale.product, "name", str(sale.product)),  # ✅ FIXED
        "quantity": sale.quantity,
        "unit_price": float(sale.unit_price),
        "total_amount": float(sale.total_amount),
        "payment_method": sale.payment_method,
        "sold_at": sale.sold_at,

        # "due_amount": float(getattr(sale, "due_amount", 0)),
        "invoice_no": getattr(sale, "invoice_no", f"INV-{sale.id}"),
    })


from .models import Staffs


@csrf_exempt
def create_staff(request):
    if request.method == "POST":
        name = request.POST.get("name")
        role = request.POST.get("role")
        specialization = request.POST.get("specialization")
        # photo = request.POST.get("photo")
        experience = request.POST.get("experience")
        phone = request.POST.get("phone")
        joining_date = request.POST.get("joining_date")
        salary = request.POST.get("salary", 0)
        status = request.POST.get("status", "Active")

        staff = Staffs.objects.create(
            # id=request.POST.get("id"),
            name=request.POST.get("name"),
            role=request.POST.get("role"),
            specialization=request.POST.get("specialization"),
            phone=request.POST.get("phone"),
            experience=request.POST.get("experience"),
            joining_date=request.POST.get("joining_date"),
            salary=request.POST.get("salary"),
            status=request.POST.get("status"),
        )

        return JsonResponse({
            "id": staff.id,
            "name": staff.name,
            "status": staff.status,
        })

    return JsonResponse(
        {"error": "Invalid request method"},
        status=405
    )

from datetime import date
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Sum
from .models import Staffs, Payment


@csrf_exempt
def get_staffs(request):
    staffs = Staffs.objects.order_by("-id")
    data = []

    for staff in staffs:
        paid_amount = Payment.objects.filter(
            staff=staff,
            payment_type="Salary"
        ).aggregate(total=Sum("amount"))["total"] or 0

        due_amount = max(float(staff.salary) - float(paid_amount), 0)

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
            # "due_amount": str(due_amount),
            "status": staff.status,
        })

    return JsonResponse(data, safe=False)


@csrf_exempt
def get_staff(request, staff_id):
    try:
        staff = Staffs.objects.get(id=staff_id)

        paid_amount = Payment.objects.filter(
            staff=staff,
            payment_type="Salary"
        ).aggregate(total=Sum("amount"))["total"] or 0

        due_amount = max(float(staff.salary) - float(paid_amount), 0)

        data = {
            "id": staff.id,
            "name": staff.name,
            "role": staff.role,
            "specialization": staff.specialization,
            "phone": staff.phone,
            "experience": staff.experience,
            "joining_date": staff.joining_date,
            "salary": str(staff.salary),
            "paid_amount": str(paid_amount),
            # "due_amount": str(due_amount),
            "status": staff.status,
        }

        return JsonResponse(data)

    except Staffs.DoesNotExist:
        return JsonResponse({"error": "Staff not found"}, status=404)



@csrf_exempt
def update_staff(request, id):
    if request.method == "POST":   # easier with FormData

        staff = Staffs.objects.get(id=id)

        staff.name = request.POST.get("name")
        staff.role = request.POST.get("role")
        staff.specialization = request.POST.get("specialization")
        staff.phone = request.POST.get("phone")
        staff.experience = request.POST.get("experience")
        staff.joining_date = request.POST.get("joining_date")
        staff.salary = request.POST.get("salary")
        staff.status = request.POST.get("status")

        staff.save()

        return JsonResponse({
            "success": True,
            "message": "Staff updated successfully"
        })

    return JsonResponse({"success": False}, status=400)

@csrf_exempt
def delete_staff(request, staff_id):
    if request.method == "DELETE":
        try:
            staff = Staffs.objects.get(id=staff_id)
            staff.delete()

            return JsonResponse({"message": "Staff deleted successfully"})

        except Staffs.DoesNotExist:
            return JsonResponse({"error": "Staff not found"},status=404)


@csrf_exempt
def pause_member(request, member_id):

    if request.method != "POST":
        return JsonResponse(
            {"error": "Invalid request"},
            status=405
        )

    try:
        member = Member.objects.get(id=member_id)

    except Member.DoesNotExist:
        return JsonResponse(
            {"error": "Member not found"},
            status=404
        )

    # -------------------------------------------------
    # ALREADY PAUSED
    # -------------------------------------------------

    if member.is_paused:
        return JsonResponse({
            "success": False,
            "message": "Member already paused",
            "paused_date": (
                member.pause_start_date.strftime("%Y-%m-%d")
                if member.pause_start_date
                else None
            )
        }, status=400)

    # -------------------------------------------------
    # READ REQUEST
    # -------------------------------------------------

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

    # -------------------------------------------------
    # CURRENT MONTH
    # -------------------------------------------------

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

    # -------------------------------------------------
    # COUNT PAUSES IN CURRENT MONTH
    # -------------------------------------------------

    pause_count = MemberPause.objects.filter(
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

    # -------------------------------------------------
    # CALCULATE USED PAUSE DAYS THIS MONTH
    # -------------------------------------------------

    previous_pauses = MemberPause.objects.filter(
        member=member,
        start_date__gte=month_start,
        start_date__lte=month_end,
        end_date__isnull=False
    )

    used_days = sum(
        pause.paused_days
        for pause in previous_pauses
    )

    remaining_days = 15 - used_days

    # -------------------------------------------------
    # NO DAYS LEFT
    # -------------------------------------------------

    if remaining_days <= 0:
        return JsonResponse({
            "success": False,
            "error": "Member has already used the maximum 15 pause days this month.",
            "used_days": used_days,
            "remaining_days": 0,
            "max_pause_days": 15
        }, status=400)

    # -------------------------------------------------
    # THIS PAUSE CAN USE ONLY REMAINING DAYS
    # -------------------------------------------------

    allowed_days = remaining_days

    # The date on which the member must be active again
    allowed_resume_date = (
        freeze_date + timedelta(days=allowed_days)
    )

    # -------------------------------------------------
    # CREATE PAUSE HISTORY
    # -------------------------------------------------

    pause = MemberPause.objects.create(
        member=member,
        start_date=freeze_date,
        allowed_days=allowed_days,
        paused_days=0
    )

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
        "allowed_resume_date": allowed_resume_date.strftime("%Y-%m-%d"),
        "status": member.status,
        "is_paused": member.is_paused,
    })

@csrf_exempt
def resume_member(request, member_id):

    if request.method != "POST":
        return JsonResponse(
            {"error": "Invalid request"},
            status=405
        )

    try:
        member = Member.objects.get(id=member_id)

    except Member.DoesNotExist:
        return JsonResponse(
            {"error": "Member not found"},
            status=404
        )

    # -------------------------------------------------
    # MEMBER NOT PAUSED
    # -------------------------------------------------

    if not member.is_paused:
        return JsonResponse({
            "success": False,
            "message": "Member is not paused"
        }, status=400)

    # -------------------------------------------------
    # READ REQUEST
    # -------------------------------------------------

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

    # -------------------------------------------------
    # GET ACTIVE PAUSE
    # -------------------------------------------------

    pause = MemberPause.objects.filter(
        member=member,
        end_date__isnull=True
    ).order_by("-start_date").first()

    if not pause:
        return JsonResponse({
            "success": False,
            "error": "Active pause record not found."
        }, status=400)

    pause_start = pause.start_date

    # -------------------------------------------------
    # RESUME DATE VALIDATION
    # -------------------------------------------------

    paused_days = (
        resume_date - pause_start
    ).days

    if paused_days <= 0:
        return JsonResponse({
            "success": False,
            "error": "Resume date must be after pause date."
        }, status=400)

    # -------------------------------------------------
    # CHECK MAXIMUM ALLOWED DAYS
    # -------------------------------------------------

    if paused_days > pause.allowed_days:
        return JsonResponse({
            "success": False,
            "error": "Pause limit exceeded.",
            "allowed_days": pause.allowed_days,
            "requested_days": paused_days,
            "max_monthly_days": 15
        }, status=400)

    # -------------------------------------------------
    # UPDATE PAUSE HISTORY
    # -------------------------------------------------

    pause.end_date = resume_date
    pause.paused_days = paused_days
    pause.save()

    # -------------------------------------------------
    # UPDATE MEMBER EXPIRY
    # -------------------------------------------------

    if member.expiry_date:
        member.expiry_date = (
            member.expiry_date +
            timedelta(days=paused_days)
        )

    # -------------------------------------------------
    # CALCULATE CURRENT MONTH USAGE
    # -------------------------------------------------

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
        member=member,
        start_date__gte=month_start,
        start_date__lte=month_end,
        end_date__isnull=False
    )

    used_days_this_month = sum(
        p.paused_days
        for p in completed_pauses
    )

    # -------------------------------------------------
    # UPDATE MEMBER STATE
    # -------------------------------------------------

    member.is_paused = False
    member.pause_start_date = None
    member.status = "Active"

    # Keep existing field updated
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
            if member.expiry_date
            else None
        ),

        "status": member.status,

        "is_paused": member.is_paused
    })


@csrf_exempt
def add_member_payment(request, member_id):

    if request.method != "POST":
        return JsonResponse(
            {"error": "Invalid request method"},
            status=405
        )

    data = json.loads(request.body)

    try:
        member = Member.objects.get(id=member_id)
    except Member.DoesNotExist:
        return JsonResponse(
            {"error": "Member not found"},
            status=404
        )

    amount = float(data.get("amount", 0))

    if amount <= 0:
        return JsonResponse(
            {"error": "Amount must be greater than 0"},
            status=400
        )

    if float(member.due_amount) <= 0:
        return JsonResponse(
            {"error": "Membership fee already fully paid"},
            status=400
        )

    if amount > float(member.due_amount):
        return JsonResponse(
            {
                "error": f"Amount cannot exceed due amount ₹{member.due_amount}"
            },
            status=400
        )

    # Income date is automatically set by auto_now_add=True
    Income.objects.create(
        member=member,
        title="Membership",
        name=member.name,
        phone=member.phone,
        category="membership",
        amount=amount,
        payment_method=data.get("payment_method", "cash"),
        description=f"Membership payment received from {member.name}",
        is_system_generated=True
    )

    member.paid_amount += amount
    member.due_amount -= amount

    if member.due_amount < 0:
        member.due_amount = 0

    member.save()

    return JsonResponse({
        "message": "Member payment recorded",
        "paid_amount": member.paid_amount,
        "due_amount": member.due_amount,
        "payment_completed": member.due_amount == 0
    })




@csrf_exempt
def add_staff_payment(request, staff_id):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON data"}, status=400)

    try:
        staff = Staffs.objects.get(id=staff_id)
    except Staffs.DoesNotExist:
        return JsonResponse({"error": "Staff not found"}, status=404)

    amount = float(data.get("amount", 0))
    payment_date = data.get("payment_date")
    payment_method = data.get("payment_method")

    if amount <= 0:
        return JsonResponse({"error": "Amount must be greater than 0"}, status=400)

    # 1) Save in Payment table -> for Transactions page
    payment = Payment.objects.create(
        staff=staff,
        amount=amount,
        payment_type="Salary",
        payment_method=payment_method,
        payment_date=payment_date,
    )

    # 2) Save in Expense table -> for expense/profit calculation

    Expense.objects.create(
    title="Salary",
    name=staff.name,
    phone=staff.phone,
    category="salary",
    amount=amount,
    payment_method=payment_method,
    date=payment_date,
    description=f"Salary paid to {staff.name}",
    is_system_generated=True
)

    return JsonResponse({
        "message": "Staff payment recorded successfully",
        "payment_id": payment.id,
        "staff_name": staff.name,
        "amount": str(payment.amount)
    }, status=201)


# from django.http import JsonResponse
# from django.views.decorators.csrf import csrf_exempt
# from .models import Payment


# @csrf_exempt
# def transactions(request):
#     payments = Payment.objects.select_related("member", "staff").order_by("-payment_date", "-id")

#     data = []

#     for payment in payments:
#         if payment.member:
#             data.append({
#                 "id": payment.id,
#                 "transaction_for": "Member",
#                 "person_id": payment.member.id,
#                 "name": payment.member.name,
#                 "phone": payment.member.phone,
#                 "amount": payment.amount,
#                 "payment_type": payment.payment_type,
#                 "payment_method": payment.payment_method,
#                 "payment_date": payment.payment_date,
#             })

#         elif payment.staff:
#             data.append({
#                 "id": payment.id,
#                 "transaction_for": "Staff",
#                 "person_id": payment.staff.id,
#                 "name": payment.staff.name,
#                 "phone": payment.staff.phone,
#                 "amount": payment.amount,
#                 "payment_type": payment.payment_type,
#                 "payment_method": payment.payment_method,
#                 "payment_date": payment.payment_date,
#             })

#     return JsonResponse(data, safe=False)





@csrf_exempt
def add_enquiry(request):
    if request.method == "POST":
        name = request.POST.get("name")
        phone = request.POST.get("phone")
        plan = request.POST.get("plan")
        date = request.POST.get("date")

        if not (phone.isdigit() and len(phone) == 10 ):
            return JsonResponse(
                {"error": "Enter a valid 10-digit mobile number"},status=400)

        enquiry = Enquiry.objects.create(
            name=name,
            phone=phone,
            plan=plan,
            date=date
        )

        return JsonResponse({
            "message": "Enquiry added",
            "name": enquiry.name,
            "phone": enquiry.phone,
            "plan": enquiry.plan,
            "date":enquiry.date
        })

    return JsonResponse({"error": "Invalid request method"}, status=405)



def view_enquiry(request):
        enquiries = Enquiry.objects.all().order_by("-id")

        data = [
            {
                "id": enquiry.id,
                "name": enquiry.name,
                "phone": enquiry.phone,
                "plan": enquiry.plan,
                "date":enquiry.date
            }
            for enquiry in enquiries
        ]

        return JsonResponse(data, safe=False)


@csrf_exempt
def delete_enquiry(request, enquiry_id):
    if request.method == "DELETE":
        enquiry = get_object_or_404(Enquiry, id=enquiry_id)
        enquiry.delete()

        return JsonResponse({
            "message": "Enquiry deleted successfully"
        })

    return JsonResponse({"error": "Invalid request method"}, status=405)


@csrf_exempt
def add_expense(request):

    if request.method != "POST":
        return JsonResponse(
            {"error": "Invalid method"},
            status=405
        )

    try:
        data = json.loads(request.body)

        expense = Expense.objects.create(
            title=data.get("title"),
            name=data.get("name"),
            phone=data.get("phone"),
            category=data.get("category"),
            description=data.get("description"),
            amount=data.get("amount"),
            payment_method=data.get("payment_method"),
            date=data.get("date"),
            is_system_generated=False
        )

        return JsonResponse({
            "message": "Expense added successfully",
            "id": expense.id
        }, status=201)


    except Exception as e:
        return JsonResponse(
            {"error": str(e)},
            status=400
        )



@csrf_exempt
def expenses(request):

    if request.method != "GET":
        return JsonResponse(
            {"error": "Invalid request method"},
            status=405
        )

    expenses = Expense.objects.all().order_by("-date", "-id")

    data = []

    for expense in expenses:
        data.append({
            "id": expense.id,
            "title": expense.title,
            "name": expense.name,
            "phone": expense.phone,
            "category": expense.category,
            "description": expense.description,
            "amount": str(expense.amount),
            "payment_method": expense.payment_method,
            "date": expense.date.strftime("%Y-%m-%d"),
            "type": "Salary" if expense.is_system_generated else "Additional"
        })

    return JsonResponse(
        data,
        safe=False
    )


@csrf_exempt
def add_income(request):

    if request.method != "POST":
        return JsonResponse(
            {"error": "Invalid request method"},
            status=405
        )

    try:
        data = json.loads(request.body)

    except json.JSONDecodeError:
        return JsonResponse(
            {"error": "Invalid JSON data"},
            status=400
        )

    member = None

    if data.get("member_id"):
        try:
            member = Member.objects.get(id=data.get("member_id"))
        except Member.DoesNotExist:
            return JsonResponse(
                {"error": "Member not found"},
                status=404
            )


    income = Income.objects.create(
        member=member,
        title=data.get("title"),
        name=data.get("name"),
        phone=data.get("phone"),
        category=data.get("category"),
        description=data.get("description"),
        amount=data.get("amount"),
        payment_method=data.get(
            "payment_method",
            "cash"
        ),
        date=data.get("date"),
        is_system_generated=False
    )


    return JsonResponse(
        {
            "message": "Additional income added successfully",
            "income_id": income.id
        },
        status=201
    )


@csrf_exempt
def incomes(request):

    if request.method != "GET":
        return JsonResponse(
            {"error": "Invalid request method"},
            status=405
        )

    data = []

    # =========================
    # NORMAL INCOME
    # =========================

    incomes = Income.objects.all().order_by("-date", "-id")

    for income in incomes:

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

    # =========================
    # PRODUCT SALES
    # =========================

    sales = Sales_product.objects.select_related(
        "member",
        "product"
    ).order_by("-sold_at", "-id")

    for sale in sales:

        data.append({
            "id": f"sa_{sale.id}",
            "title": "Product Sale",
            "name": sale.product.name,

            # Member phone number
            "phone": sale.member.phone if sale.member else "",

            "category": "Product",
            "description": f"{sale.product.name} × {sale.quantity}",
            "amount": str(sale.total_amount),
            "payment_method": sale.payment_method,
            "date": sale.sold_at.strftime("%Y-%m-%d"),
            "type": "Product Sale",

            "_sort_date": sale.sold_at,
        })

    # =========================
    # SORT NEWEST FIRST
    # =========================

    data.sort(
        key=lambda x: x["_sort_date"],
        reverse=True
    )

    # Remove internal sorting field
    for item in data:
        item.pop("_sort_date", None)

    return JsonResponse(data, safe=False)


@csrf_exempt
def income_by_members(request):

    if request.method != "GET":
        return JsonResponse(
            {"error": "GET request only"},
            status=405
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

    # ================================
    # BASE FILTER
    # ================================

    base_income = Income.objects.filter(
        date__date__gte=start_date,
        date__date__lte=end_date
    )

    # ================================
    # BASIC
    # Silver + Gold
    # ================================

    basic_income = base_income.filter(
        category="membership",
        member__plan__in=[
            "Silver",
            "Gold"
        ]
    ).aggregate(
        total=Sum("amount")
    )["total"] or 0

    # ================================
    # PREMIUM
    # Premium + Platinum
    # ================================

    premium_income = base_income.filter(
        category="membership",
        member__plan__in=[
            "Premium",
            "Platinum"
        ]
    ).aggregate(
        total=Sum("amount")
    )["total"] or 0


    other_income = base_income.filter(
        category__in=[
            "registration",
            "product_sale",
            "other"
        ]
    ).aggregate(
        total=Sum("amount")
    )["total"] or 0

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
            }
        ]
    })

@csrf_exempt
def expense_by_category(request):

    if request.method != "GET":
        return JsonResponse(
            {"error": "GET request only"},
            status=405
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

    expenses = (
        Expense.objects
        .filter(
            date__gte=start_date,
            date__lte=end_date
        )
        .values("category")
        .annotate(
            total=Sum("amount")
        )
        .order_by("-total")
    )

    data = []

    for expense in expenses:
        data.append({
            "category": expense["category"],
            "amount": float(
                expense["total"] or 0
            )
        })

    return JsonResponse({
        "success": True,
        "period": period,
        "start_date": start_date,
        "end_date": end_date,
        "expenses": data
    })



from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Sum
from datetime import date

@csrf_exempt
def profit_loss_report(request):

    if request.method != "GET":
        return JsonResponse(
            {"error": "GET request only"},
            status=405
        )

    period = request.GET.get("period")
    selected_date = request.GET.get("date")

    from_date = request.GET.get("from_date")
    to_date = request.GET.get("to_date")

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

    if start_date is None:
        return JsonResponse(
            {"error": "Invalid period"},
            status=400
        )

    # ---------------------------------------
    # MEMBERSHIP INCOME
    # ---------------------------------------

    incomes = Income.objects.filter(
       date__gte=start_date,
       date__lte=end_date
    )

    income_members = []

    total_membership_income = 0

    for income in incomes:

        amount = float(income.amount)

        total_membership_income += amount

        income_members.append({
            "member": income.member.name if income.member else "-",
            "amount": amount,
            "payment_method": income.payment_method,
            "date": income.date.strftime("%d-%m-%Y")
        })

    # ---------------------------------------
    # PRODUCT SALES
    # ---------------------------------------

    sales = Sales_product.objects.select_related(
        "member",
        "product"
    ).filter(
        sold_at__date__gte=start_date,
        sold_at__date__lte=end_date
    )

    sales_list = []

    sales_category = {}

    total_sales = 0

    for sale in sales:

        amount = float(sale.total_amount)

        total_sales += amount

        category = sale.product.category or "Other"

        sales_category[category] = (
            sales_category.get(category, 0) + amount
        )

        sales_list.append({
            "member": sale.member.name if sale.member else "-",
            "product": sale.product.name,
            "category": category,
            "quantity": sale.quantity,
            "amount": amount,
            "date": sale.sold_at.strftime("%d-%m-%Y %H:%M")
        })

    # ---------------------------------------
    # EXPENSES
    # ---------------------------------------

    expenses = Expense.objects.filter(
        date__gte=start_date,
        date__lte=end_date
    )

    expense_list = []

    expense_category = {}

    total_expense = 0

    for expense in expenses:

        amount = float(expense.amount)

        total_expense += amount

        category = expense.category

        expense_category[category] = (
            expense_category.get(category, 0) + amount
        )

        expense_list.append({
            "category": category,
            "amount": amount,
            "date": expense.date.strftime("%d-%m-%Y"),
            "description": expense.description
        })

    # ---------------------------------------
    # KPIs
    # ---------------------------------------

    total_income = total_membership_income + total_sales
    net_profit = total_income - total_expense

    # ---------------------------------------
    # RESPONSE
    # ---------------------------------------

    return JsonResponse({

        "success": True,

        "period": period,

        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),

        "kpis": {

            "membership_income": total_membership_income,

            "product_sales": total_sales,

            "total_income": total_income,

            "total_expense": total_expense,

            "net_profit": net_profit
        },

        "sales_category": sales_category,

        "expense_category": expense_category,

        "income_members": income_members,

        "sales": sales_list,

        "expenses": expense_list

    })



from django.conf import settings
from groq import Groq

@api_view(["POST"])
def generate_diet(request):
    print("USER:", request.user)
    print("AUTH:", request.auth)
    member_id = request.data.get("member_id")

    if not member_id:
        return JsonResponse(
            {
                "success": False,
                "error": "member_id is required."
            },
            status=400
        )

    member = get_object_or_404(Member, id=member_id)

    age = member.age
    gender = member.gender
    height = member.height
    weight = member.weight
    # goal = member.goal
    # food = member.food_preference

    client = Groq(api_key=settings.GROQ_API_KEY)

    prompt = f"""
You are an expert sports nutritionist.

Create a one-day personalized diet plan.

Member Details

Age: {age}
Gender: {gender}
Height: {height} cm
Weight: {weight} kg

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

  
  }},
  "nutrition": {{
    "daily_calories": "",
    "protein": "",
    "carbohydrates": "",
    "fat": "",
    "water": ""
  }},
  "meals": [
    {{
      "meal": "Breakfast",
      "time": "",
      "foods": [],
      "calories": ""
    }},
    {{
      "meal": "Morning Snack",
      "time": "",
      "foods": [],
      "calories": ""
    }},
    {{
      "meal": "Lunch",
      "time": "",
      "foods": [],
      "calories": ""
    }},
    {{
      "meal": "Evening Snack",
      "time": "",
      "foods": [],
      "calories": ""
    }},
    {{
      "meal": "Dinner",
      "time": "",
      "foods": [],
      "calories": ""
    }},
    {{
      "meal": "Before Bed",
      "time": "",
      "foods": [],
      "calories": ""
    }}
  ],
  "supplements": [],
  "foods_to_avoid": [],
  "shopping_list": [],
  "tips": []
}}
"""

    chat = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": "You are a certified sports nutritionist."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.7,
    )

    ai_response = chat.choices[0].message.content

    try:
        diet_json = json.loads(ai_response)

    except json.JSONDecodeError:

        return JsonResponse(
            {
                "success": False,
                "error": "AI returned invalid JSON.",
                "raw_response": ai_response
            },
            status=500
        )

    return JsonResponse(
        {
            "success": True,
            "diet_plan": diet_json
        }
    )


# .....................helper 

import json
import requests

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from rest_framework.decorators import api_view

from groq import Groq

from .models import Member


EXERCISE_API_URL = "https://exercisedb.p.rapidapi.com/exercises/name/"

def build_gif_url(exercise_id, resolution="360"):
    if not exercise_id:
        return None
    return (
        f"https://exercisedb.p.rapidapi.com/image"
        f"?exerciseId={exercise_id}"
        f"&resolution={resolution}"
        f"&rapidapi-key={settings.EXERCISE_API_KEY}"
    )

def search_exercise(exercise_name):
    """
    Search ExerciseDB and return the first matching exercise.
    """

    try:
        response = requests.get(
            f"{EXERCISE_API_URL}{exercise_name}",
            headers={
                "X-RapidAPI-Key": settings.EXERCISE_API_KEY,
                "X-RapidAPI-Host": "exercisedb.p.rapidapi.com",
            },
            timeout=10,
        )

        if response.status_code != 200:
            return None

        data = response.json()

        if not isinstance(data, list) or len(data) == 0:
            return None

        exercise = data[0]

        return {
            "id": exercise.get("id"),
            "name": exercise.get("name"),
            "gifUrl": build_gif_url(exercise.get("id")),
            "bodyPart": exercise.get("bodyPart"),
            "target": exercise.get("target"),
            "equipment": exercise.get("equipment"),
            "secondaryMuscles": exercise.get("secondaryMuscles", []),
            "instructions": exercise.get("instructions", []),
        }

    except Exception as e:
        print("ExerciseDB Error:", e)
        return None

import re





@api_view(["POST"])
def generate_workout(request):

    member_id = request.data.get("member_id")

    if not member_id:
        return JsonResponse(
            {"success": False, "error": "member_id is required."},
            status=400
        )

    member = get_object_or_404(Member, id=member_id)

    age = member.age
    gender = member.gender
    height = float(member.height)
    weight = float(member.weight)

    if height <= 0 or weight <= 0:
        return JsonResponse(
            {"success": False, "error": "Invalid height or weight for this member."},
            status=400
        )

    bmi = round(weight / ((height / 100) ** 2), 1)

    if bmi < 18.5:
        bmi_status = "Underweight"
    elif bmi < 25:
        bmi_status = "Normal"
    elif bmi < 30:
        bmi_status = "Overweight"
    else:
        bmi_status = "Obese"

    client = Groq(api_key=settings.GROQ_API_KEY)

    prompt = f"""
You are a certified strength and conditioning coach.

Create a personalized 6-day workout plan based on the member's BMI.

Member Details

Age: {age}
Gender: {gender}
Height: {height} cm
Weight: {weight} kg
BMI: {bmi}
BMI Category: {bmi_status}

Rules:

1. Workout MUST match BMI.
2. Underweight → muscle gain.
3. Normal → balanced hypertrophy.
4. Overweight → fat loss + cardio.
5. Obese → beginner friendly + low impact.

Generate:

Day 1 - Legs
Day 2 - Chest & Triceps
Day 3 - Back & Biceps
Day 4 - Shoulders
Day 5 - Cardio & Core
Day 6 - Full Body

Each day should contain 5-7 exercises.

VERY IMPORTANT:

Use REAL ExerciseDB exercise names only.

Examples:

barbell squat
leg press
walking on treadmill
bench press
push up
lat pulldown
seated cable row
dumbbell shoulder press
plank
crunch
mountain climber
burpee
romanian deadlift
leg extension
leg curl
pec deck fly
cable crossover
tricep pushdown
barbell curl
hammer curl
deadlift
lunges
hip thrust
jump rope

Return ONLY VALID JSON.

Do not return markdown.

Do not return explanations.

Return exactly this structure:

{{
    "member": {{
        "age": {age},
        "gender": "{gender}",
        "height": {height},
        "weight": {weight},
        "bmi": {bmi},
        "category": "{bmi_status}"
    }},
    "weekly_plan": [
        {{
            "day": "Day 1",
            "title": "Legs",
            "duration": "",
            "intensity": "",
            "focus": "",
            "exercises": [
                {{
                    "name": "",
                    "description": "",
                    "sets": "",
                    "reps": "",
                    "rest": ""
                }}
            ]
        }},
        {{
            "day": "Day 2",
            "title": "Chest & Triceps",
            "duration": "",
            "intensity": "",
            "focus": "",
            "exercises": []
        }},
        {{
            "day": "Day 3",
            "title": "Back & Biceps",
            "duration": "",
            "intensity": "",
            "focus": "",
            "exercises": []
        }},
        {{
            "day": "Day 4",
            "title": "Shoulders",
            "duration": "",
            "intensity": "",
            "focus": "",
            "exercises": []
        }},
        {{
            "day": "Day 5",
            "title": "Cardio & Core",
            "duration": "",
            "intensity": "",
            "focus": "",
            "exercises": []
        }},
        {{
            "day": "Day 6",
            "title": "Full Body",
            "duration": "",
            "intensity": "",
            "focus": "",
            "exercises": []
        }}
    ]
}}
"""

    try:
        chat = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are an expert certified gym trainer."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
        )
        ai_response = chat.choices[0].message.content
    except Exception as e:
        return JsonResponse(
            {"success": False, "error": f"AI request failed: {str(e)}"},
            status=502
        )

    # Strip markdown fences in case the model ignores the "no markdown" instruction
    cleaned_response = ai_response.strip()
    cleaned_response = re.sub(r"^```(?:json)?|```$", "", cleaned_response, flags=re.MULTILINE).strip()

    try:
        workout_json = json.loads(cleaned_response)

        # ----------------------------------------
        # Enrich workout with ExerciseDB data
        # ----------------------------------------
        for day in workout_json.get("weekly_plan", []):

            for exercise in day.get("exercises", []):

                exercise_name = exercise.get("name", "").strip()

                if not exercise_name:
                    continue

                exercise_data = search_exercise(exercise_name)

                if exercise_data:
                    exercise["exercise_id"] = exercise_data["id"]
                    exercise["gifUrl"] = exercise_data["gifUrl"]
                    exercise["bodyPart"] = exercise_data["bodyPart"]
                    exercise["target"] = exercise_data["target"]
                    exercise["equipment"] = exercise_data["equipment"]
                    exercise["secondaryMuscles"] = exercise_data["secondaryMuscles"]
                    exercise["instructions"] = exercise_data["instructions"]
                else:
                    exercise["exercise_id"] = None
                    exercise["gifUrl"] = None
                    exercise["bodyPart"] = ""
                    exercise["target"] = ""
                    exercise["equipment"] = ""
                    exercise["secondaryMuscles"] = []
                    exercise["instructions"] = []

    except json.JSONDecodeError:
        return JsonResponse(
            {
                "success": False,
                "error": "AI returned invalid JSON.",
                "raw_response": ai_response
            },
            status=500
        )

    return JsonResponse(
        {"success": True, "workout_plan": workout_json}
    )

    # Part 3 starts here...
    
# from rest_framework.decorators import api_view
# from rest_framework.response import Response
# from .models import DietPlanPDF
# from .serializers import DietPlanPDFSerializer


# @api_view(["POST"])
# def upload_diet_pdf(request):

#     serializer = DietPlanPDFSerializer(
#         data=request.data,
#         context={
#             "request": request
#         }
#     )

#     if serializer.is_valid():

#         serializer.save()

#         return Response({
#             "success": True,
#             "pdf_url": serializer.data["pdf"]
#         })


#     return Response(
#         serializer.errors,
#         status=400
#     )