from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Branch, Expense, Payment, Product, Trainer, TrainerPayment, Member,Expense
import json
from datetime import datetime


#.......................... MEMBERS


@csrf_exempt
def create_member(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        # Member ID
        last_member = Member.objects.order_by("-id").first()
        next_id = f"{int(last_member.id) + 1:04d}" if last_member else "0001"

        # Plan name from React
        plan_name = request.POST.get("plan")

        if not plan_name:
            return JsonResponse({"error": "Plan is required"}, status=400)

        # Join date
        join_date_str = request.POST.get("join_date")

        if not join_date_str:
            return JsonResponse({"error": "Join date is required"}, status=400)

        join_date = datetime.strptime(join_date_str, "%Y-%m-%d").date()

        # Duration based on selected plan name
        plan_days = {
            "Monthly": 30,
            "Quarterly": 90,
            "Half Yearly": 180,
            "Yearly": 365,
            "Premium": 365,
        }

        days = plan_days.get(plan_name, 0)
        expiry_date = join_date + timedelta(days=days)

        paid_amount = float(request.POST.get("paid_amount") or 0)

        photo = request.FILES.get("photo")

        member = Member.objects.create(
            id=next_id,
            name=request.POST.get("name"),
            phone=request.POST.get("phone"),
            email=request.POST.get("email"),
            plan=request.POST.get("plan"),
            join_date=join_date,
            photo=photo,
            height=request.POST.get("height"),
            weight=request.POST.get("weight"),
            age=request.POST.get("age"),
            blood_group=request.POST.get("blood_group"),
            location=request.POST.get("location"),
            adhaar_number=request.POST.get("adhaar_number"),
            gender=request.POST.get("gender"),
            paid_amount=paid_amount,
            due_amount=0,
            expiry_date=expiry_date,
            status="Active",
        )

        return JsonResponse({
            "id": member.id,
            "name": member.name,
            "plan": member.plan,
            "status": member.status,
            "expiry_date": member.expiry_date,
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

from datetime import date, timedelta

@csrf_exempt
def get_members(request):
    if request.method == "GET":

        today = date.today()

        # Block members 7 days after expiry
        Member.objects.filter(
            expiry_date__lt=today - timedelta(days=7),
            status="Active"
        ).update(status="Blocked")

        members = list(
            Member.objects.order_by('id').values()
        )

        return JsonResponse(members, safe=False)
    

@csrf_exempt
def get_member(request, member_id):
    if request.method == "GET":
        try:
            member = Member.objects.values().get(id=member_id)
            return JsonResponse(member)
        except Member.DoesNotExist:
            return JsonResponse({"error": "Member not found"},status=404)


@csrf_exempt
def update_member(request, member_id):
    if request.method == "POST":
        try:
            member = Member.objects.get(id=member_id)
        except Member.DoesNotExist:
            return JsonResponse({"error": "Member not found"}, status=404)

        member.name = request.POST.get("name")
        member.phone = request.POST.get("phone")
        member.email = request.POST.get("email")
        member.plan = request.POST.get("plan")  # <-- plan name
        member.join_date = request.POST.get("join_date")
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

        member.save()

        return JsonResponse({"message": "Member updated successfully"})

    return JsonResponse({"error": "Invalid request method"},status=405)



@csrf_exempt
def delete_member(request, member_id):
    if request.method == "DELETE":
        try:
            member = Member.objects.get(id=member_id)
            member.delete()

            return JsonResponse({"message": "Member deleted successfully"})

        except Member.DoesNotExist:
            return JsonResponse({"error": "Member not found"},status=404)


# ..............................TRAINER 

@csrf_exempt
def create_trainer(request):
    if request.method == "POST":

        trainer = Trainer.objects.create(
            name=request.POST.get("name"),
            specialization=request.POST.get("specialization"),
            phone=request.POST.get("phone"),
            experience=request.POST.get("experience"),
            salary=request.POST.get("salary"),
            join_date=request.POST.get("join_date"),
            photo=request.FILES.get("photo")  
        )

        return JsonResponse({
            "id": trainer.id,
            "message": "Trainer created"
        })

    return JsonResponse({"error": "Invalid request method"}, status=405)


@csrf_exempt
def get_trainers(request):
    if request.method == "GET":
        trainers = list(Trainer.objects.order_by('id').values())
        return JsonResponse(trainers, safe=False)

@csrf_exempt
def get_single_trainer(request, trainer_id):
    if request.method == "GET":
        try:
            trainer = Trainer.objects.values().get(id=trainer_id)
            return JsonResponse(trainer, safe=False)
        except Trainer.DoesNotExist:
            return JsonResponse({"error": "Trainer not found"},status=404)


@csrf_exempt
def update_trainer(request, trainer_id):
    if request.method == "POST":

        try:
            trainer = Trainer.objects.get(id=trainer_id)

            trainer.name = request.POST.get("name")
            trainer.specialization = request.POST.get("specialization")
            trainer.phone = request.POST.get("phone")
            trainer.experience = request.POST.get("experience")
            trainer.salary = request.POST.get("salary")
            trainer.join_date = request.POST.get("join_date")

          
            if request.FILES.get("photo"):
                trainer.photo = request.FILES.get("photo")

            trainer.save()

            return JsonResponse({"message": "Trainer updated"})

        except Trainer.DoesNotExist:
            return JsonResponse({"error": "Trainer not found"},status=404)

    return JsonResponse({"error": "Invalid request method"}, status=405)



@csrf_exempt
def delete_trainer(request, trainer_id):
    if request.method == "DELETE":
        try:
            trainer = Trainer.objects.get(id=trainer_id)
            trainer.delete()

            return JsonResponse({"message": "Trainer deleted"})

        except Trainer.DoesNotExist:

            return JsonResponse({"error": "Trainer not found"},status=404)


@csrf_exempt
def get_trainer_payments(request):
    if request.method == "GET":
        payments = TrainerPayment.objects.all().values()
        return JsonResponse(list(payments), safe=False)

    return JsonResponse({"error": "Invalid request method"}, status=405)


@csrf_exempt
def get_single_trainer_payment(request,trainer_id):
    if request.method == "GET":
        try:
            trainer=TrainerPayment.objects.values().get(id=trainer_id)
            return JsonResponse(trainer,safe=False)
        except TrainerPayment.DoesNotExist:
            return JsonResponse({"error": "Trainer not found"},status=404)



@csrf_exempt
def add_trainer_payment(request, trainer_id):
    if request.method == "POST":

        TrainerPayment.objects.create(
            trainer_id=trainer_id,
            amount=request.POST.get("amount"),
            payment_date=request.POST.get("payment_date"),
            type=request.POST.get("type", "Salary"),
            notes=request.POST.get("notes"),
            for_month=request.POST.get("for_month")
        )

        return JsonResponse({
            "message": "Trainer payment recorded"
        })

    return JsonResponse({"error": "Invalid request method"}, status=405)


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


@csrf_exempt
def get_dashboard_stats(request):
    if request.method == "GET":

        today = date.today()
        blocked_members = Member.objects.filter(
    status="Blocked"
).count()

        total_members = Member.objects.count()
        active_members = Member.objects.filter(status="Active").count()
        pending_payments = Member.objects.filter(due_amount__gt=0).count()
        next_week = today + timedelta(days=7)
        expiries = Member.objects.filter(expiry_date__range=[today, next_week]).order_by('expiry_date')

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
                
                "plan": m.plan,
                
                # "photo": m.photo.url if m.photo else None,
                "join_date": m.join_date
            }
            for m in recent
        ]

        trainers_count = Trainer.objects.count()

# ...........................INCOME

        total_income = Payment.objects.aggregate(
            total=Sum("amount")
        )["total"] or 0

        today_income = Payment.objects.filter(
            payment_date=today
        ).aggregate(total=Sum("amount"))["total"] or 0

        monthly_income = Payment.objects.filter(
            payment_date__year=today.year,
            payment_date__month=today.month
        ).aggregate(total=Sum("amount"))["total"] or 0

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

# .............................LOSS AND PROFIT

        today_profit = max(today_income - today_expense, 0)
        total_profit = max(total_income - total_expense, 0)
        monthly_profit = max(monthly_income - monthly_expense, 0)
        today_loss = max(today_expense - today_income, 0)
        total_loss = max(total_expense - total_income, 0)
        monthly_loss = max(monthly_expense - monthly_income, 0)
        net_profit = total_profit

        return JsonResponse({
            "total_members": total_members,
            "active_members": active_members,
            "blocked_members": blocked_members,
            "active_members_growth": "+5.2%",

            "trainers_count": trainers_count,
            "trainers_growth": "+2",

            "total_income": total_income,
            "today_income": today_income,
            "monthly_income": monthly_income,

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

            "revenue_growth": "+12%",
            "expense_growth": "+8%",
            "profit_growth": "+15%",

            "pending_payments": pending_payments,
            "upcoming_expiries": len(upcoming_expiries_list),
            "upcoming_expiries_list": upcoming_expiries_list,
            "recent_registrations": recent_registrations
        })


@csrf_exempt
def pause_member(request, member_id):
    if request.method == "POST":
        try:
            member = Member.objects.get(id=member_id)
        except Member.DoesNotExist:
            return JsonResponse({"message": "Member not found"},status=404)

        if member.status == "Paused":
            return JsonResponse({"message": "Member is already paused"},status=400)

        member.status = "Paused"
        member.pause_start_date = date.today()
        member.save()

        return JsonResponse({
            "message": "Membership paused",
            "status": "Paused"
        })
    



@csrf_exempt
def resume_member(request, member_id):
    if request.method == "POST":
        try:
            member = Member.objects.get(id=member_id)
        except Member.DoesNotExist:
            return JsonResponse(
                {"message": "Member not found"},
                status=404
            )

        if member.status != "Paused":
            return JsonResponse({"message": "Member is not paused"},status=400)

        days_paused = (
            date.today() - member.pause_start_date
        ).days

        member.expiry_date = (
            member.expiry_date +
            timedelta(days=days_paused)
        )

        member.status = "Active"
        member.pause_start_date = None
        member.save()

        return JsonResponse({
            "message": "Membership resumed",
            "status": "Active",
            "new_expiry_date": member.expiry_date
        })
    

    
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.db.models import Sum
from .models import Member, Payment

@csrf_exempt
def add_payment(request, member_id):
    if request.method == "POST":

        member = Member.objects.get(id=member_id)

        Payment.objects.create(
            member=member,
            amount=request.POST.get("amount"),
            payment_date=request.POST.get("payment_date"),
            payment_method=request.POST.get("payment_method"),
            payment_type=request.POST.get("payment_type")
        )

        total_paid = Payment.objects.filter(
            member=member
        ).aggregate(
            total=Sum("amount")
        )["total"] or 0

        member.paid_amount = float(total_paid)

        member.due_amount = max(
            float(member.plan.price) - float(total_paid),
            0
        )

        member.save()

        return JsonResponse({
            "message": "Payment recorded successfully",
            "paid_amount": member.paid_amount,
            "due_amount": member.due_amount
        })

    return JsonResponse(
        {"error": "Invalid request method"},
        status=405
    )
    


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
    if request.method == "POST":
        try:
            member = Member.objects.get(id=member_id)
        except Member.DoesNotExist:
            return JsonResponse({"message": "Member not found"},status=404)

        duration = int(request.POST.get("duration"))
        today = date.today()

        if member.expiry_date and member.expiry_date > today:
            member.expiry_date += timedelta(days=duration)
        else:
            member.expiry_date = today + timedelta(days=duration)

        member.status = "Active"
        member.save()

        return JsonResponse({
            "message": "Membership renewed",
            "new_expiry_date": member.expiry_date
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
        blocked_members = list(
            Member.objects.filter(status="Blocked").values()
        )

        return JsonResponse(blocked_members, safe=False)
    

@csrf_exempt
def send_whatsapp(request, member_id):
    member = Member.objects.get(id=member_id)

    return JsonResponse({
        "id": member.id,
        "name": member.name,
        "phone": member.phone,
        "due_amount": member.due_amount,
        "expiry_date": str(member.expiry_date)
    })




def expiring_soon_members(request):
    today = date.today()
    next_3_days = today + timedelta(days=3)

    members = Member.objects.filter(
        expiry_date__range=[today, next_3_days],
        status="Active"
    ).values(
        "id",
        "name",
        "phone",
        "expiry_date",
        "due_amount"  
    )

    return JsonResponse(list(members), safe=False)

import json

@csrf_exempt
def create_product(request):
    if request.method == "POST":
        data = json.loads(request.body)

        product = Product.objects.create(
            name=data.get("name"),
            description=data.get("description"),
            price=data.get("price"),
            stock=data.get("stock"),
            category=data.get("category"),
        )

        return JsonResponse({"message": "Product created"})

# READ
def get_products(request):
    products = Product.objects.all()
    data = []
    for product in products:
        data.append({
            "id": product.id,
            "name": product.name,
            "description": product.description,
            "price": product.price,
            "stock": product.stock,
            "category": product.category,
            # "image": product.image.url if product.image else None,
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
import json

@csrf_exempt
def update_product(request, product_id):
    if request.method == "POST":
        data = json.loads(request.body)

        product = Product.objects.get(id=product_id)

        product.name = data.get("name", product.name)
        product.description = data.get("description", product.description)
        product.price = data.get("price", product.price)
        product.stock = data.get("stock", product.stock)
        product.category = data.get("category", product.category)

        product.save()

        return JsonResponse({"message": "Updated"})
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