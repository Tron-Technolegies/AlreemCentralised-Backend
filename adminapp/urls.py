from django.urls import path
from . import views

urlpatterns = [

    path('members/', views.get_members, name='get_members'),
    path('members/create/', views.create_member, name='create_member'),
    path('members/<str:member_id>/', views.get_member, name='get_member'),
    path('members/<str:member_id>/update/', views.update_member, name='update_member'),
    path('members/<str:member_id>/delete/', views.delete_member, name='delete_member'),

    path('trainers/', views.get_trainers),
    path('trainers/create/', views.create_trainer),
    path('trainers/<str:trainer_id>/', views.get_trainer, name='get_trainer'),
    path('trainers/<int:trainer_id>/update/', views.update_trainer),
    path('trainers/<int:trainer_id>/delete/', views.delete_trainer),

    path('trainers/<int:trainer_id>/payments/',views.get_trainer_payments),
    path('trainers/<int:trainer_id>/payments/add/',views.add_trainer_payment),

    path('plans/', views.get_plans, name='get_plans'),
    path('plans/create/', views.create_plan, name='create_plan'),
    path('plans/<int:plan_id>/update/', views.update_plan, name='update_plan'),
    path('plans/<int:plan_id>/delete/', views.delete_plan, name='delete_plan'),

    # path('members/<str:member_id>/renew/', views.renew_member, name='renew_member'),
    # path('members/next-id/generate/', views.get_next_member_id, name='get_next_member_id'),
    # path('members/<str:member_id>/pause/', views.pause_member, name='pause_member'),
    # path('members/<str:member_id>/resume/', views.resume_member, name='resume_member'),
    # path('members/<str:member_id>/payments/', views.get_payments, name='get_payments'),
    # path('members/<str:member_id>/payments/add/', views.add_payment, name='add_payment'),
    path('branches/', views.get_branches, name='get_branches'),
    path('branches/create/', views.create_branch, name='create_branch'),
    path('branches/<int:branch_id>/update/', views.update_branch, name='update_branch'),
    path('branches/<int:branch_id>/delete/', views.delete_branch, name='delete_branch'),
]