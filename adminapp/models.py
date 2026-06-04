from django.db import models


class Member(models.Model):
    id = models.CharField(max_length=100, primary_key=True)
    name = models.CharField(max_length=255, null=True, blank=True)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True, null=True)
    plan = models.CharField(max_length=100, blank=True, null=True)
    duration = models.CharField(max_length=100, blank=True, null=True)
    join_date = models.CharField(max_length=50, blank=True, null=True)
    status = models.CharField(max_length=50, blank=True, null=True)
    photo = models.CharField(max_length=500, blank=True, null=True)
    height = models.FloatField(blank=True, null=True)
    weight = models.FloatField(blank=True, null=True)
    bmi = models.FloatField(blank=True, null=True)
    age = models.IntegerField(blank=True, null=True)
    blood_group = models.CharField(max_length=20, blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    adhaar_number = models.CharField(max_length=50, blank=True, null=True)
    paid_amount = models.FloatField(blank=True, null=True)
    due_amount = models.FloatField(blank=True, null=True)
    expiry_date = models.CharField(max_length=50, blank=True, null=True)
    gender = models.CharField(max_length=20, blank=True, null=True)
    pause_start_date = models.CharField(max_length=50, blank=True, null=True)




class Plan(models.Model):
    name = models.CharField(max_length=100)
    duration = models.CharField(max_length=100)
    price = models.FloatField()




class Trainer(models.Model):
    name = models.CharField(max_length=255)
    specialization = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    photo = models.CharField(max_length=500, blank=True, null=True)
    experience = models.CharField(max_length=100, blank=True, null=True)
    salary = models.FloatField(blank=True, null=True)
    join_date = models.CharField(max_length=50, blank=True, null=True)




class Branch(models.Model):
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255)
    manager_name = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    capacity = models.IntegerField(blank=True, null=True)




class Payment(models.Model):
    member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        db_column='member_id'
    )
    amount = models.FloatField()
    payment_date = models.CharField(max_length=50)
    payment_method = models.CharField(max_length=100, blank=True, null=True)
    type = models.CharField(max_length=100, blank=True, null=True)




class TrainerPayment(models.Model):
    trainer = models.ForeignKey(
        Trainer,
        on_delete=models.CASCADE,
        db_column='trainer_id'
    )
    amount = models.FloatField()
    payment_date = models.CharField(max_length=50)
    payment_method = models.CharField(max_length=100, blank=True, null=True)
    type = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    for_month = models.CharField(max_length=50, blank=True, null=True)




class Setting(models.Model):
    key = models.CharField(max_length=255, primary_key=True)
    value = models.TextField()
