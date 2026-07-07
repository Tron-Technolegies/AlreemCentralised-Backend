from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Branch, Enquiry, Expense, Payment, Product, Sales_product, Member,Expense
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
        join_date_str = request.POST.get("join_date")
        phone = request.POST.get("phone", "").strip()

        if not plan_id:
            return JsonResponse({"error": "Plan is required"}, status=400)

        if not join_date_str:
            return JsonResponse({"error": "Join date is required"}, status=400)

        # Phone validation
        if not (phone.isdigit() and len(phone) == 10):
            return JsonResponse(
                {"error": "Enter a valid 10-digit mobile number"},
                status=400
            )

        # Get selected plan from DB
        try:
            plan = Plan.objects.get(id=plan_id)
        except Plan.DoesNotExist:
            return JsonResponse({"error": "Invalid plan selected"}, status=400)

        # Parse join date
        join_date = datetime.strptime(join_date_str, "%Y-%m-%d").date()

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
            paid_amount = 0

        plan_amount = float(plan.price or 0)
        due_amount = max(plan_amount - paid_amount, 0)

        photo = request.FILES.get("photo")

        member = Member.objects.create(
            id=next_id,
            name=request.POST.get("name"),
            phone=phone,
            email=request.POST.get("email"),
            plan=plan.name,   # if your Member.plan field is CharField
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
            "id": member.id,
            "name": member.name,
            "plan": member.plan,
            "status": member.status,
            "expiry_date": member.expiry_date,
            "bmi": member.bmi,
            "due": member.due_amount
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    
    

from datetime import date
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def get_members(request):
    if request.method == "GET":
        today = date.today()
        members = Member.objects.all().order_by("id")   # keep ID order
        data = []

        for member in members:
            if member.is_paused:
                member.status = "Paused"

            elif member.expiry_date:
                if member.expiry_date < today:
                    days_expired = (today - member.expiry_date).days

                    if days_expired <= 7:
                        member.status = "Expired"
                    else:
                        member.status = "Blocked"
                else:
                    member.status = "Active"

            member.save()

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
                "join_date": member.join_date,
                "expiry_date": member.expiry_date,
                "pause_start_date": member.pause_start_date,
                "is_paused": member.is_paused,
                "paid_amount": member.paid_amount,
                "due_amount": member.due_amount,
                "status": member.status,
                "adhaar_number": member.adhaar_number,
                "photo": member.photo.url if member.photo else None,
            })

        return JsonResponse(data, safe=False)

@csrf_exempt
def get_member(request, member_id):
    if request.method == "GET":
        try:
            member = Member.objects.get(id=member_id)

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
                "join_date": member.join_date,
                "expiry_date": member.expiry_date,
                "pause_start_date": member.pause_start_date,
                "is_paused": member.is_paused,
                "paid_amount": member.paid_amount,
                "due_amount": member.due_amount,
                "status": member.status,
                "adhaar_number": member.adhaar_number,
                "photo": member.photo.url if member.photo else None,
            }

            return JsonResponse(data)

        except Member.DoesNotExist:
            return JsonResponse({"error": "Member not found"}, status=404)


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

@csrf_exempt
def get_dashboard_stats(request):
    if request.method == "GET":

        today = date.today()
        if today.month == 1:
            last_month = 12
            last_year = today.year - 1
        else:
            last_month = today.month - 1
            last_year = today.year

        blocked_members = Member.objects.filter(status="Blocked").count()
        total_members = Member.objects.count()
        active_members = Member.objects.filter(status="Active").count()
        expired_members = Member.objects.filter(status="Expired").count()
        paused_members = Member.objects.filter(is_paused=True).count()
        pending_payments = Member.objects.filter(due_amount__gt=0).count()
        next_week = today + timedelta(days=7)
        # expiries = Member.objects.filter(expiry_date__range=[today, next_week]).order_by('expiry_date')
        expiries = Member.objects.filter(status="Active",expiry_date__gte=today,expiry_date__lte=next_week).order_by('expiry_date')

        upcoming_expiries_list = [
                {
                    "name": m.name,
                    "phone": m.phone,
                    "expiry_date": m.expiry_date,
                    "due_amount": m.due_amount,
                }
                for m in expiries
            ]

        recent = Member.objects.order_by('-id')[:5]

        recent_registrations = [
            {
                "name": m.name,

                "phone": m.phone,

                "email":m.email,
                
                "plan": m.plan,
                
                "join_date": m.join_date
            }
            for m in recent
        ]
        

        # Membership income
        membership_total_income = Payment.objects.aggregate(
            total=Sum("amount")
        )["total"] or 0

        membership_today_income = Payment.objects.filter(
            payment_date=today
        ).aggregate(total=Sum("amount"))["total"] or 0

        membership_monthly_income = Payment.objects.filter(
            payment_date__year=today.year,
            payment_date__month=today.month
        ).aggregate(total=Sum("amount"))["total"] or 0

        # Product income
        product_total_income = Sales_product.objects.aggregate(
            total=Sum("total_amount")
        )["total"] or 0

        product_today_income = Sales_product.objects.filter(
            sold_at=today
        ).aggregate(total=Sum("total_amount"))["total"] or 0

        product_monthly_income = Sales_product.objects.filter(
            sold_at__year=today.year,
            sold_at__month=today.month
        ).aggregate(total=Sum("total_amount"))["total"] or 0

        last_month_membership_income = Payment.objects.filter(
            payment_date__year=last_year,
            payment_date__month=last_month
        ).aggregate(total=Sum("amount"))["total"] or 0

        last_month_product_income = Sales_product.objects.filter(
            sold_at__year=last_year,
            sold_at__month=last_month
        ).aggregate(total=Sum("total_amount"))["total"] or 0

        last_month_income = (
            last_month_membership_income +
            last_month_product_income
        )

        # Combined income
        total_income = membership_total_income + product_total_income
        today_income = membership_today_income + product_today_income
        monthly_income = membership_monthly_income + product_monthly_income

#........................EXPENSE 

        total_expense = Expense.objects.aggregate(
            total=Sum("amount")
        )["total"] or 0

        today_expense = Expense.objects.filter(
            date=today
        ).aggregate(total=Sum("amount"))["total"] or 0

        monthly_expense = Expense.objects.filter(
            date__year=today.year,
            date__month=today.month
        ).aggregate(total=Sum("amount"))["total"] or 0

        last_month_expense = Expense.objects.filter(
            date__year=last_year,
            date__month=last_month
        ).aggregate(total=Sum("amount"))["total"] or 0

        last_month_profit = max(
            last_month_income - last_month_expense,
            0
        )

# .............................LOSS AND PROFIT

        today_profit = max(today_income - today_expense, 0)
        total_profit = max(total_income - total_expense, 0)
        monthly_profit = max(monthly_income - monthly_expense, 0)
        today_loss = max(today_expense - today_income, 0)
        total_loss = max(total_expense - total_income, 0)
        monthly_loss = max(monthly_expense - monthly_income, 0)
        net_profit = total_profit

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
            last_month_profit
        )


        return JsonResponse({
            "total_members": total_members,
            "active_members": active_members,
            "blocked_members": blocked_members,
            "expired_members": expired_members,
            "paused_members": paused_members,

            "total_income": total_income,
            "today_income": today_income,
            "monthly_income": monthly_income,

            "membership_total_income": membership_total_income,
            "product_total_income": product_total_income,

            "total_expense": total_expense,
            "today_expense": today_expense,
            "monthly_expense": monthly_expense,

            "today_profit": today_profit,
            "total_profit": total_profit,
            "monthly_profit":monthly_profit,

            "today_loss": today_loss,
            "total_loss": total_loss,
            "monthly_loss":monthly_loss,

            "net_profit": net_profit,

            "revenue_growth": revenue_growth,
            "expense_growth": expense_growth,
            "profit_growth": profit_growth,

            "pending_payments": pending_payments,
            "upcoming_expiries": len(upcoming_expiries_list),
            "upcoming_expiries_list": upcoming_expiries_list,
            "recent_registrations": recent_registrations
        })



from django.db.models import Sum
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404

@csrf_exempt
@require_http_methods(["POST"])
def add_payment(request, member_id):

    member = get_object_or_404(Member, id=member_id)

    amount = request.POST.get("amount")

    if not amount:
        return JsonResponse(
            {"error": "Amount is required"},
            status=400
        )

    Payment.objects.create(
        member=member,
        amount=amount,
        payment_date=request.POST.get("payment_date"),
        payment_method=request.POST.get("payment_method"),
        payment_type=request.POST.get("payment_type")
    )

    total_paid = (
        Payment.objects.filter(member=member)
        .aggregate(total=Sum("amount"))["total"] or 0
    )

    # Get plan object using the plan name stored in member.plan
    plan = get_object_or_404(Plan, name=member.plan)

    member.paid_amount = total_paid
    member.due_amount = max(
        float(plan.price) - float(total_paid),
        0
    )

    member.save()

    return JsonResponse({
        "message": "Payment recorded successfully",
        "paid_amount": member.paid_amount,
        "due_amount": member.due_amount
    })


def get_single_payment(request, member_id):
    payments = Payment.objects.filter(member_id=member_id).values()
    return JsonResponse(list(payments),safe=False)


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

    plan_days = {
        "Silver": 30,
        "Gold": 60,
        "Premium": 90,
        "Platinum": 180,
        "Diamond": 365,
    }

    duration = plan_days.get(plan_name)

    if not duration:
        return JsonResponse({"message": "Invalid plan"}, status=400)

    today = date.today()

    # Active member renewing before expiry
    if member.expiry_date and member.expiry_date >= today:
        member.expiry_date += timedelta(days=duration)
    else:
        # Expired / Blocked member
        member.expiry_date = today + timedelta(days=duration)

    member.plan = plan_name
    member.status = "Active"

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

@csrf_exempt
def get_single_product(request, product_id):
    if request.method == "GET":
        try:
            product = Product.objects.get(id=product_id)

            data = {
                "id": product.id,
                "name": product.name,
                "description": product.description,
                "price": product.price,
                "stock": product.stock,
                "category": product.category,
                # "image": product.image.url if product.image else None,
            }

            return JsonResponse(data, safe=False)

        except Product.DoesNotExist:
            return JsonResponse(
                {"error": "Product not found"},
                status=404
            )

    return JsonResponse(
        {"error": "Invalid request method"},
        status=400
    )

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
    sales = Sales_product.objects.select_related("product").all().order_by("-sold_at")

    data = []

    for sale in sales:
        data.append({
            "id": sale.id,
            "member_id": sale.member.id if sale.member else None,
            "member_name": sale.member.name if sale.member else None,
            "product": sale.product.name,
            "quantity": sale.quantity,
            "payment_method":sale.payment_method,
            "unit_price": float(sale.unit_price),
            "total_amount": float(sale.total_amount),
            "sold_at": sale.sold_at.strftime("%d-%m-%Y %H:%M")
        })
    return JsonResponse({
        "success": True,
        "sales": data
    })


def today_sales(request):
    today = timezone.now().date()

    sales = Sales_product.objects.filter(
        sold_at__date=today
    )

    total_sales = sales.aggregate(
        total=Sum("total_amount")
    )["total"] or 0

    total_products_sold = sales.aggregate(
        total=Sum("quantity")
    )["total"] or 0

    return JsonResponse({
        "sales": [
            {
                "today_sales": float(total_sales),
                "products_sold": total_products_sold,
                "sales_count": sales.count()
            }
        ]
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
    staffs = Staffs.objects.order_by("id")
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


import json
from datetime import datetime
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def pause_member(request, member_id):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=405)

    try:
        member = Member.objects.get(id=member_id)
    except Member.DoesNotExist:
        return JsonResponse({"error": "Member not found"}, status=404)

    if member.is_paused:
        return JsonResponse({
            "message": "Member already paused",
            "paused_date": member.pause_start_date,
        })

    body = json.loads(request.body)

    freeze_date = datetime.strptime(
        body["freeze_date"],
        "%Y-%m-%d"
    ).date()

    member.is_paused = True
    member.pause_start_date = freeze_date
    member.status = "Paused"
    member.save()

    return JsonResponse({
        "message": "Member paused successfully",
        "paused_date": member.pause_start_date.strftime("%Y-%m-%d"),
        "status": member.status,
        "is_paused": member.is_paused,
    })





import json

@csrf_exempt
def resume_member(request, member_id):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=405)

    try:
        member = Member.objects.get(id=member_id)
    except Member.DoesNotExist:
        return JsonResponse({"error": "Member not found"}, status=404)

    if not member.is_paused:
        return JsonResponse({"message": "Member is not paused"})

    body = json.loads(request.body)

    resume_date = datetime.strptime(
        body["resume_date"],
        "%Y-%m-%d"
    ).date()

    pause_start = member.pause_start_date

    paused_days = (resume_date - pause_start).days

    if paused_days < 0:
        paused_days = 0

    member.expiry_date = member.expiry_date + timedelta(days=paused_days)

    member.is_paused = False
    member.pause_start_date = None
    member.status = "Active"

    member.save()

    return JsonResponse({
        "message": "Member resumed successfully",
        "paused_days_added": paused_days,
        "new_expiry_date": member.expiry_date.strftime("%Y-%m-%d"),
        "status": member.status,
        "is_paused": member.is_paused
    })


import json
from datetime import datetime
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Member

@csrf_exempt
def pause_member(request, member_id):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=405)

    try:
        member = Member.objects.get(id=member_id)
    except Member.DoesNotExist:
        return JsonResponse({"error": "Member not found"}, status=404)

    if member.is_paused:
        return JsonResponse({"message": "Member is already paused"})

    body = json.loads(request.body)

    freeze_date = datetime.strptime(
        body["freeze_date"],
        "%Y-%m-%d"
    ).date()

    member.is_paused = True
    member.pause_start_date = freeze_date
    member.status = "Paused"
    member.save()

    return JsonResponse({
        "message": "Member paused successfully",
        "pause_start_date": member.pause_start_date.strftime("%Y-%m-%d"),
        "status": member.status,
        "is_paused": member.is_paused
    })

# ..............................TRAINER 

# @csrf_exempt
# def create_trainer(request):
#     if request.method == "POST":

#         trainer = Trainer.objects.create(
#             name=request.POST.get("name"),
#             specialization=request.POST.get("specialization"),
#             phone=request.POST.get("phone"),
#             experience=request.POST.get("experience"),
#             salary=request.POST.get("salary"),
#             join_date=request.POST.get("join_date"),
#             photo=request.FILES.get("photo")  
#         )

#         return JsonResponse({
#             "id": trainer.id,
#             "message": "Trainer created"
#         })

#     return JsonResponse({"error": "Invalid request method"}, status=405)


# @csrf_exempt
# def get_trainers(request):
#     if request.method == "GET":
#         trainers = list(Trainer.objects.order_by('id').values())
#         return JsonResponse(trainers, safe=False)

# @csrf_exempt
# def get_single_trainer(request, trainer_id):
#     if request.method == "GET":
#         try:
#             trainer = Trainer.objects.values().get(id=trainer_id)
#             return JsonResponse(trainer, safe=False)
#         except Trainer.DoesNotExist:
#             return JsonResponse({"error": "Trainer not found"},status=404)


# @csrf_exempt
# def update_trainer(request, trainer_id):
#     if request.method == "POST":

#         try:
#             trainer = Trainer.objects.get(id=trainer_id)

#             trainer.name = request.POST.get("name")
#             trainer.specialization = request.POST.get("specialization")
#             trainer.phone = request.POST.get("phone")
#             trainer.experience = request.POST.get("experience")
#             trainer.salary = request.POST.get("salary")
#             trainer.join_date = request.POST.get("join_date")

          
#             if request.FILES.get("photo"):
#                 trainer.photo = request.FILES.get("photo")

#             trainer.save()

#             return JsonResponse({"message": "Trainer updated"})

#         except Trainer.DoesNotExist:
#             return JsonResponse({"error": "Trainer not found"},status=404)

#     return JsonResponse({"error": "Invalid request method"}, status=405)



# @csrf_exempt
# def delete_trainer(request, trainer_id):
#     if request.method == "DELETE":
#         try:
#             trainer = Trainer.objects.get(id=trainer_id)
#             trainer.delete()

#             return JsonResponse({"message": "Trainer deleted"})

#         except Trainer.DoesNotExist:

#             return JsonResponse({"error": "Trainer not found"},status=404)




# @csrf_exempt
# def get_single_trainer_payment(request,trainer_id):
#     if request.method == "GET":
#         try:
#             trainer=TrainerPayment.objects.values().get(id=trainer_id)
#             return JsonResponse(trainer,safe=False)
#         except TrainerPayment.DoesNotExist:
#             return JsonResponse({"error": "Trainer not found"},status=404)



import json
from django.http import JsonResponse
from .models import Member, Payment
@csrf_exempt
def add_member_payment(request, member_id):
    if request.method == "POST":
        data = json.loads(request.body)
        print("member_id =", member_id)
        member = Member.objects.get(id=member_id)

        amount = float(data.get("amount", 0))

        # Amount must be positive
        if amount <= 0:
            return JsonResponse(
                {"error": "Amount must be greater than 0"},
                status=400
            )

        # Already fully paid
        if float(member.due_amount) <= 0:
            return JsonResponse(
                {"error": "Membership fee already fully paid"},
                status=400
            )

        # Prevent overpayment
        if amount > float(member.due_amount):
            return JsonResponse(
                {"error": f"Amount cannot exceed due amount ₹{member.due_amount}"},
                status=400
            )

        Payment.objects.create(
            member=member,
            amount=amount,
            payment_date=data.get("payment_date"),
            payment_type=data.get("payment_type"),
            payment_method=data.get("payment_method"),
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

    return JsonResponse(
        {"error": "Invalid request method"},
        status=405
    )


import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Staffs, Payment, Expense


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
        title=f"Salary - {staff.name}",
        category="salary",
        amount=amount,
        date=payment_date,
        description=f"Salary paid to {staff.name} via {payment_method}"
    )

    return JsonResponse({
        "message": "Staff payment recorded successfully",
        "payment_id": payment.id,
        "staff_name": staff.name,
        "amount": str(payment.amount)
    }, status=201)


from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Payment


@csrf_exempt
def transactions(request):
    payments = Payment.objects.select_related("member", "staff").order_by("-payment_date", "-id")

    data = []

    for payment in payments:
        if payment.member:
            data.append({
                "id": payment.id,
                "transaction_for": "Member",
                "person_id": payment.member.id,
                "name": payment.member.name,
                "phone": payment.member.phone,
                "amount": payment.amount,
                "payment_type": payment.payment_type,
                "payment_method": payment.payment_method,
                "payment_date": payment.payment_date,
            })

        elif payment.staff:
            data.append({
                "id": payment.id,
                "transaction_for": "Staff",
                "person_id": payment.staff.id,
                "name": payment.staff.name,
                "phone": payment.staff.phone,
                "amount": payment.amount,
                "payment_type": payment.payment_type,
                "payment_method": payment.payment_method,
                "payment_date": payment.payment_date,
            })

    return JsonResponse(data, safe=False)





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


