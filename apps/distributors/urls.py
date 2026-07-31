from django.urls import path
from .views.auth import distributor_login, distributor_logout
from .views.dashboard import dashboard, save_invite_message
from .views.leads import leads
from .views.profile import profile_edit, profile_update
from .views.agents import agents_index, agents_create, agents_store, agents_show

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
    path('distributor/agents/store/', agents_store, name='agents_store'),
    path('distributor/agents/<int:pk>/', agents_show, name='agents_show'),
]
