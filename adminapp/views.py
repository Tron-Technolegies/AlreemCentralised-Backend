from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Trainer, TrainerPayment
from .models import Member
import json
from datetime import datetime


#.......................... MEMBERS

@csrf_exempt
def create_member(request):
    if request.method == "POST":

        last_member = Member.objects.order_by('-id').first()

        if last_member:
            next_id = f"{int(last_member.id) + 1:04d}"
        else:
            next_id = "0001"

        member = Member.objects.create(
            id=next_id,
            name=request.POST.get("name"),
            phone=request.POST.get("phone"),
            email=request.POST.get("email"),
            plan=request.POST.get("plan"),
            duration=request.POST.get("duration"),
            join_date=request.POST.get("join_date"),
            photo=request.POST.get("photo"),
            height=request.POST.get("height"),
            weight=request.POST.get("weight"),
            age=request.POST.get("age"),
            blood_group=request.POST.get("blood_group"),
            location=request.POST.get("location"),
            adhaar_number=request.POST.get("adhaar_number"),
            gender=request.POST.get("gender"),
            paid_amount=request.POST.get("paid_amount"),
            due_amount=request.POST.get("due_amount"),
            expiry_date=request.POST.get("expiry_date"),
            status="Active"
        )

        return JsonResponse({
            "id": member.id,
            "status": member.status
        })
    

@csrf_exempt
def get_members(request):
    if request.method == "GET":
        members = list(Member.objects.values())
        return JsonResponse(members, safe=False)
    

@csrf_exempt
def get_member(request, member_id):
    if request.method == "GET":
        try:
            member = Member.objects.values().get(id=member_id)
            return JsonResponse(member)
        except Member.DoesNotExist:
            return JsonResponse(
                {"error": "Member not found"},status=404)


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
        member.plan = request.POST.get("plan")
        member.duration = request.POST.get("duration")
        member.join_date = request.POST.get("join_date")
        member.height = request.POST.get("height")
        member.weight = request.POST.get("weight")
        member.age = request.POST.get("age")
        member.blood_group = request.POST.get("blood_group")
        member.location = request.POST.get("location")
        member.adhaar_number = request.POST.get("adhaar_number")
        member.gender = request.POST.get("gender")
        member.paid_amount = request.POST.get("paid_amount")
        member.due_amount = request.POST.get("due_amount")
        member.expiry_date = request.POST.get("expiry_date")

        if request.POST.get("status"):
            member.status = request.POST.get("status")

        if request.FILES.get("photo"):
            member.photo = request.FILES.get("photo")

        member.save()

        return JsonResponse({"message": "Member updated successfully"})

    return JsonResponse(
        {"error": "Invalid request method"},
        status=405
    )

@csrf_exempt
def delete_member(request, member_id):
    if request.method == "DELETE":
        try:
            member = Member.objects.get(id=member_id)
            member.delete()

            return JsonResponse({
                "message": "Member deleted successfully"
            })

        except Member.DoesNotExist:
            return JsonResponse(
                {"error": "Member not found"},
                status=404
            )


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
            photo=request.FILES.get("photo")  # file upload
        )

        return JsonResponse({
            "id": trainer.id,
            "message": "Trainer created"
        })

    return JsonResponse({"error": "Invalid request method"}, status=405)


@csrf_exempt
def get_trainers(request):
    if request.method == "GET":
        trainers = list(Trainer.objects.values())
        return JsonResponse(trainers, safe=False)

@csrf_exempt
def get_trainer(request, trainer_id):
    if request.method == "GET":
        try:
            trainer = Trainer.objects.values().get(id=trainer_id)
            return JsonResponse(trainer, safe=False)
        except Trainer.DoesNotExist:
            return JsonResponse(
                {"error": "Trainer not found"},
                status=404
            )


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
            return JsonResponse(
                {"error": "Trainer not found"},status=404)

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
def get_trainer_payments(request, trainer_id):
    if request.method == "GET":
        payments = list(
            TrainerPayment.objects.filter(trainer_id=trainer_id).values()
        )
        return JsonResponse(payments, safe=False)

    return JsonResponse({"error": "Invalid request method"}, status=405)

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
        plans = list(Plan.objects.values())
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
        

        from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Branch
import json


@csrf_exempt
def get_branches(request):
    if request.method == "GET":
        branches = list(Branch.objects.values())
        return JsonResponse(branches, safe=False)


@csrf_exempt
def create_branch(request):
    if request.method == "POST":
        data = json.loads(request.body)

        branch = Branch.objects.create(
            name=data.get("name"),
            location=data.get("location"),
            manager_name=data.get("manager_name"),
            phone=data.get("phone"),
            capacity=data.get("capacity")
        )

        return JsonResponse({"message": "success"})
            # "id": branch.id,
            # "name": branch.name,
            # "location": branch.location,
            # "manager_name": branch.manager_name,
            # "phone": branch.phone,
            # "capacity": branch.capacity
        # })


@csrf_exempt
def update_branch(request, branch_id):
    if request.method == "PUT":
        try:
            branch = Branch.objects.get(id=branch_id)
        except Branch.DoesNotExist:
            return JsonResponse(
                {"error": "Branch not found"},
                status=404
            )

        data = json.loads(request.body)

        branch.name = data.get("name")
        branch.location = data.get("location")
        branch.manager_name = data.get("manager_name")
        branch.phone = data.get("phone")
        branch.capacity = data.get("capacity")

        branch.save()

        return JsonResponse({
            "message": "Branch updated successfully"
        })


@csrf_exempt
def delete_branch(request, branch_id):
    if request.method == "DELETE":
        try:
            branch = Branch.objects.get(id=branch_id)
            branch.delete()

            return JsonResponse({
                "message": "Branch deleted successfully"
            })

        except Branch.DoesNotExist:
            return JsonResponse(
                {"error": "Branch not found"},
                status=404
            )