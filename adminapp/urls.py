from django.urls import path
from django.conf.urls.static import static
from alreem import settings
from . import views

urlpatterns = [

    path('members/', views.get_members, name='get_members'),
    path('members/create/', views.create_member, name='create_member'),
    path("members/get_payments/",views.get_payments,name="get_payments"),
    path('members/<str:member_id>/', views.get_member, name='get_member'),
    path('members/<str:member_id>/update/', views.update_member, name='update_member'),
    path('members/<str:member_id>/delete/', views.delete_member, name='delete_member'),

    # path('trainers/', views.get_trainers,name="get_trainers"),
    # path('trainers/payments/', views.get_trainer_payments, name="get_trainer_payments"),
    # path('trainers/create/', views.create_trainer,name="create_trainer"),
    # path('trainers/<str:trainer_id>/', views.get_single_trainer, name='get_trainer'),
    # path('trainers/<int:trainer_id>/update/', views.update_trainer,name="update_trainer"),
    # path('trainers/<int:trainer_id>/delete/', views.delete_trainer,name="delete_trainer"),
    # path('trainers/<int:trainer_id>/payments/add/', views.add_trainer_payment,name="add_trainer_payment"),
    # path('trainers/<int:trainer_id>/single_payments/', views.get_single_trainer_payment,name="get_single_trainer_payment"),

    path('plans/', views.get_plans, name='get_plans'),
    path('plans/create/', views.create_plan, name='create_plan'),
    path('plans/<int:plan_id>/update/', views.update_plan, name='update_plan'),
    path('plans/<int:plan_id>/delete/', views.delete_plan, name='delete_plan'),

    path('branches/', views.get_branches, name='get_branches'),
    path('branches/create/', views.create_branch, name='create_branch'),
    path('branches/<int:branch_id>/update/', views.update_branch, name='update_branch'),
    path('branches/<int:branch_id>/delete/', views.delete_branch, name='delete_branch'),
    path('dashboard/', views.get_dashboard_stats,name="get_dashboard_stats"),

    path('members/pause/<str:member_id>/',views.pause_member,name="pause_member"),
    path('members/resume/<str:member_id>/',views.resume_member, name="resume_member"),
    path('members/<str:member_id>/payments/add/', views.add_payment, name='add_payment'),
    path('members/<str:member_id>/single_payment/', views.get_single_payment, name='get_single_payment'),
    path('members/<str:member_id>/renew/', views.renew_member, name='renew_member'),

    path('expenses/', views.add_expense, name='add_expense'),
    path('view_expenses/', views.view_expenses, name='view_expenses'),
    path('blocked_members/', views.get_blocked_members, name='blocked_members'),
    path("expiring_soon_members/", views.expiring_soon_members, name='expiring_soon_members'),

    path('send_whatsapp/<str:member_id>/', views.send_whatsapp, name='send_whatsapp'),

    path("products/", views.get_products,name="get_products"),
    path("products/create/", views.create_product,name="create_product"),
    path("products/<int:product_id>/", views.get_single_product,name="get_single_product"),
    path("products/update/<int:product_id>/", views.update_product,name="update_product"),
    path("products/delete/<int:product_id>/", views.delete_product,name="delete_product"),

    path("sell_product/", views.sell_product,name="sell_product"),
    path("sales_list/", views.sales_list,name="sales_list"),
    path("today_sales/", views.today_sales,name="today_sales"),
    path("validate_member/<str:member_id>/", views.validate_member,name="validate_member"),
    path("one_sale/<int:sale_id>/", views.one_sale,name="one_sale"),

    path("staff/create/", views.create_staff,name="create_staff"),
    path("staff/get/", views.get_staffs,name="get_staffs"),
    path("staff/get/<int:staff_id>/", views.get_staff,name="get_single_staffs"),
    path("staff/update/<int:id>/", views.update_staff,name="update_staff"),
    path("staff/delete/<int:staff_id>/", views.delete_staff,name="delete_staff"),
    # path("today_sales/", views.today_sales,name="today_sales"),


    path("member/pause/<str:member_id>/",views.pause_member,name="pause_member"),
    path("member/resume/<str:member_id>/",views.resume_member,name="resume_member")


] 

