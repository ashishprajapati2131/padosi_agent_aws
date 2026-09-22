from django.urls import path
from .views.auth import distributor_login, distributor_logout
from .views.dashboard import dashboard, save_invite_message
from .views.leads import leads
from .views.profile import profile_edit, profile_update
from .views.agents import agents_index, agents_create, agents_show, agents_resume_payment
from .views.sub_distributors import (
    sub_distributors_index,
    sub_distributor_create,
    sub_distributor_toggle_status,
    sub_distributor_agents,
    sub_distributor_join,
    sub_distributor_login,
    sub_distributor_logout,
    sub_distributor_dashboard,
    sub_distributor_register_agent,
)

app_name = 'distributors'

urlpatterns = [
    path('distributor-login/', distributor_login, name='login'),
    path('distributor-logout/', distributor_logout, name='logout'),
    
    path('distributor/dashboard/', dashboard, name='dashboard'),
    path('distributor/dashboard/invite-message/', save_invite_message, name='dashboard_invite_message'),
    
    path('distributor/leads/', leads, name='leads'),
    
    path('distributor/profile/', profile_edit, name='profile'),
    path('distributor/profile/update/', profile_update, name='profile_update'),
    
    path('distributor/agents/', agents_index, name='agents_index'),
    path('distributor/agents/create/', agents_create, name='agents_create'),
    path('distributor/agents/<int:pk>/', agents_show, name='agents_show'),
    path('distributor/agents/<int:pk>/resume-payment/', agents_resume_payment, name='agents_resume_payment'),

    # Sub-Distributors management (Distributor Portal)
    path('distributor/sub-distributors/', sub_distributors_index, name='sub_distributors_index'),
    path('distributor/sub-distributors/create/', sub_distributor_create, name='sub_distributor_create'),
    path('distributor/sub-distributors/<int:pk>/toggle/', sub_distributor_toggle_status, name='sub_distributor_toggle_status'),
    path('distributor/sub-distributors/<int:pk>/agents/', sub_distributor_agents, name='sub_distributor_agents'),

    # Public Sub-Distributor candidate onboarding link
    path('sub-distributor/join/<str:dist_code>/', sub_distributor_join, name='sub_distributor_join'),

    # Sub-Distributor dedicated portal
    path('sub-distributor/login/', sub_distributor_login, name='sub_distributor_login'),
    path('sub-distributor/logout/', sub_distributor_logout, name='sub_distributor_logout'),
    path('sub-distributor/dashboard/', sub_distributor_dashboard, name='sub_distributor_dashboard'),
    path('sub-distributor/agents/create/', sub_distributor_register_agent, name='sub_distributor_register_agent'),
]
