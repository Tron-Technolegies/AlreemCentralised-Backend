from django.db import models
from cloudinary.models import CloudinaryField


class Member(models.Model):
    id = models.CharField(max_length=100, primary_key=True)
    name = models.CharField(max_length=255, null=True, blank=True)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True, null=True)
    plan = models.CharField(max_length=100, null=True, blank=True)
    branch = models.CharField(max_length=100, null=True, blank=True)  
    join_date = models.CharField(max_length=50, blank=True, null=True)
    status = models.CharField(max_length=50, blank=True, null=True)
    photo = CloudinaryField("image",blank=True, null=True)
    height = models.FloatField(blank=True, null=True)
    weight = models.FloatField(blank=True, null=True)
    bmi = models.FloatField(blank=True, null=True, editable=False)
    age = models.IntegerField(blank=True, null=True)
    blood_group = models.CharField(max_length=20, blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    adhaar_number = models.CharField(max_length=50, blank=True, null=True)
    paid_amount = models.FloatField(default=0)
    due_amount = models.FloatField(default=0)
    expiry_date = models.DateField(blank=True, null=True, editable=False)
    gender = models.CharField(max_length=20, blank=True, null=True)
    is_paused = models.BooleanField(default=False)
    pause_start_date = models.DateField(blank=True, null=True)
    used_pause_days = models.PositiveIntegerField(default=0)


class Plan(models.Model):
    name = models.CharField(max_length=100)
    duration = models.IntegerField()
    price = models.FloatField()

class Trainer(models.Model):
    name = models.CharField(max_length=255)
    specialization = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    photo = models.CharField(max_length=500, blank=True, null=True)
    experience = models.CharField(max_length=100, blank=True, null=True)
    salary = models.FloatField(blank=True, null=True)
    join_date = models.CharField(max_length=50, blank=True, null=True)



class Staffs(models.Model):
    ROLE_CHOICES = [
        ("Trainer", "Trainer"),
        ("Receptionist", "Receptionist"),
        ("Manager", "Manager"),
        ("Accountant", "Accountant"),
        ("Cleaner", "Cleaner"),
    ]

    STATUS_CHOICES = [
        ("Active", "Active"),
        ("Inactive", "Inactive"),
    ]
    name = models.CharField(max_length=100, blank=True, null=True)
    role = models.CharField(max_length=100, blank=True, null=True)
    specialization = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    experience = models.CharField(max_length=50, blank=True, null=True)
    joining_date = models.DateField(blank=True, null=True)
    salary = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="Active"
    )



class Branch(models.Model):
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255)
    manager_name = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    capacity = models.IntegerField(blank=True, null=True)


class Payment(models.Model):
    member = models.ForeignKey(Member,on_delete=models.CASCADE,null=True,blank=True)
    staff = models.ForeignKey(Staffs,on_delete=models.CASCADE,null=True,blank=True)
    PAYMENT_METHOD_CHOICES = [
        ("Cash", "Cash"),
        ("Card", "Card"),
        ("UPI", "UPI"),
        ("Wallet", " Wallet"),]
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateField()
    payment_method = models.CharField(max_length=50,choices=PAYMENT_METHOD_CHOICES,blank=True,null=True)
    payment_type = models.CharField(max_length=100,blank=True,null=True)



class Expense(models.Model):

    CATEGORY_CHOICES = [
        ("salary", "Salary"),
        ("rent", "Rent"),
        ("utilities", "Utilities"),
        ("maintenance", "Maintenance"),
        ("marketing", "Marketing"),
        ("equipment", "Equipment"),
        ("misc", "Miscellaneous"),
    ]

    PAYMENT_METHOD_CHOICES = [
        ("cash", "Cash"),
        ("upi", "UPI"),
        ("card", "Card"),
        ("bank", "Bank Transfer"),
    ]

    title = models.CharField(max_length=100)
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True, null=True)

    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES
    )

    description = models.TextField(blank=True, null=True)

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default="cash"
    )

    date = models.DateField()

    # True for salary entries created automatically
    # False for manually added expenses
    is_system_generated = models.BooleanField(default=False)


class Income(models.Model):

    CATEGORY_CHOICES = [
        ("membership", "Membership Fee"),
        ("product_sale", "Product Sale"),
        ("registration", "Registration Fee"),
        ("other", "Other"),
    ]

    PAYMENT_METHOD_CHOICES = [
        ("cash", "Cash"),
        ("upi", "UPI"),
        ("card", "Card"),
        ("bank", "Bank Transfer"),
    ]
    member = models.ForeignKey(Member,on_delete=models.SET_NULL,null=True,blank=True)
    title = models.CharField(max_length=100)
    name = models.CharField(max_length=100, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    category = models.CharField(max_length=50,choices=CATEGORY_CHOICES)
    description = models.TextField(blank=True,null=True)
    amount = models.DecimalField(max_digits=10,decimal_places=2)
    payment_method = models.CharField(max_length=20,choices=PAYMENT_METHOD_CHOICES,default="cash")
    date = models.DateTimeField(auto_now_add=True)

    # True when generated automatically (example: product sale/member payment)
    # False when manually added
    is_system_generated = models.BooleanField(default=False)



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



# class Setting(models.Model):
#     key = models.CharField(max_length=255, primary_key=True)
#     value = models.TextField()

class Product(models.Model):
    name = models.CharField(max_length=255)
    CATEGORY_CHOICES = [
        ("supplements", "Supplements"),
        ("equipment", "Equipment"),
        ("accessories", "Gym Accessories"),
        ("apparel", "Gym Apparel"),
        ("nutrition", "Nutrition & Drinks"),
        ("other", "Other"),
    ]
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField(default=0)
    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        default="supplements"
    )
    image = CloudinaryField("image",blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # payment_method = models.CharField(max_length=20, default="cash")


class Sales_product(models.Model):
    member = models.ForeignKey(Member,on_delete=models.SET_NULL,null=True,blank=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10,decimal_places=2)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    sold_at = models.DateTimeField(auto_now_add=True)
    payment_method = models.CharField(max_length=20, default="cash")


class Enquiry(models.Model):
    name = models.CharField(max_length=255, null=True, blank=True)
    phone = models.CharField(max_length=20)
    plan=models.CharField(max_length=100, null=True, blank=True)
    date = models.CharField(max_length=50, blank=True, null=True)

    





