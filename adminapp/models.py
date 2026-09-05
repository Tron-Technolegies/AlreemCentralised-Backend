from django.db import models
from cloudinary.models import CloudinaryField



class Tenant(models.Model):
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(unique=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class TenantBaseModel(models.Model):
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="%(class)s_set"
    )

    class Meta:
        abstract = True

class Plan(TenantBaseModel):
    name = models.CharField(max_length=100)
    duration = models.IntegerField()
    price = models.FloatField()

class Branch(TenantBaseModel):
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255)
    manager_name = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    capacity = models.IntegerField(blank=True, null=True)

    def __str__(self):
        return f"{self.tenant.name} - {self.name}"

from django.contrib.auth.models import AbstractUser


class CustomUser(AbstractUser):

    ROLE_CHOICES = [
        ("SUPER_ADMIN", "Super Admin"),
        ("TENANT_ADMIN", "Tenant Admin"),
        ("BRANCH_ADMIN", "Branch Admin"),
        ("STAFF", "Staff"),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="users"
    )

    branch = models.ForeignKey(
        Branch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users"
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default="STAFF"
    )

    def __str__(self):
        return self.username

class Member(TenantBaseModel):
    id = models.CharField(max_length=100, primary_key=True)
    name = models.CharField(max_length=255, null=True, blank=True)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True, null=True)
    # plan = models.CharField(max_length=100, null=True, blank=True)
    # branch = models.CharField(max_length=100, null=True, blank=True)  
    plan = models.ForeignKey(Plan,on_delete=models.PROTECT,related_name="members",null=True,blank=True)
    branch = models.ForeignKey(Branch,on_delete=models.PROTECT,related_name="members",null=True,blank=True)
    join_date = models.CharField(max_length=50, blank=True, null=True)
    status = models.CharField(max_length=50, blank=True, null=True)
    photo = CloudinaryField("image",blank=True, null=True)
    height = models.FloatField(blank=True, null=True)
    weight = models.FloatField(blank=True, null=True)
    bmi = models.FloatField(blank=True, null=True, editable=False)
    age = models.IntegerField(blank=True, null=True)
    goal = models.CharField(max_length=50,
        choices=[
        ("weight_loss", "Weight Loss"),
        ("weight_gain", "Weight Gain"),
        ("muscle_gain", "Muscle Gain"),
        ("maintenance", "Maintenance"),
        ],blank=True,null=True,)
    food_category = models.CharField(max_length=50,
            choices=[
            ("vegetarian", "Vegetarian"),
            ("non_vegetarian", "Non-Vegetarian"),
            ("vegan", "Vegan"),
            ],blank=True,null=True,)
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
    pause_expiry_date = models.DateField(blank=True,null=True)

class MemberPause(TenantBaseModel):
    member = models.ForeignKey(Member,on_delete=models.CASCADE,related_name="pause_history")
    start_date = models.DateField()
    end_date = models.DateField(null=True,blank=True)
    allowed_days = models.PositiveIntegerField(default=0)
    paused_days = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return f"{self.member.name} - {self.start_date}"

class Staffs(TenantBaseModel):
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

    role = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    specialization = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    phone = models.CharField(
        max_length=15,
        blank=True,
        null=True
    )

    experience = models.CharField(
        max_length=50,
        blank=True,
        null=True
    )

    joining_date = models.DateField(
        blank=True,
        null=True
    )

    salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="Active"
    )

    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="staff_members",
        null=True,
        blank=True
    )

    def __str__(self):
        return self.name or "Staff"
    
class Payment(TenantBaseModel):
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

class Expense(TenantBaseModel):

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
    category = models.CharField(max_length=50,choices=CATEGORY_CHOICES)
    description = models.TextField(blank=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=5)
    payment_method = models.CharField(max_length=20,choices=PAYMENT_METHOD_CHOICES,default="cash")
    date = models.DateField()
    is_system_generated = models.BooleanField(default=False)


class Income(TenantBaseModel):

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
    is_system_generated = models.BooleanField(default=False)

class Product(TenantBaseModel):
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
    category = models.CharField(max_length=50,choices=CATEGORY_CHOICES,default="supplements")
    image = CloudinaryField("image",blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # payment_method = models.CharField(max_length=20, default="cash")


class Sales_product(TenantBaseModel):
    member = models.ForeignKey(Member,on_delete=models.SET_NULL,null=True,blank=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10,decimal_places=2)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    sold_at = models.DateTimeField(auto_now_add=True)
    payment_method = models.CharField(max_length=20, default="cash")

class Enquiry(TenantBaseModel):
    name = models.CharField(max_length=255, null=True, blank=True)
    phone = models.CharField(max_length=20)
    plan=models.CharField(max_length=100, null=True, blank=True)
    date = models.CharField(max_length=50, blank=True, null=True)

class GymEquipment(TenantBaseModel):
    name = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
