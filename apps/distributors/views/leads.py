from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from apps.agents.models import AgentLead
from apps.distributors.views.dashboard import is_distributor

@login_required(login_url='distributors:login')
@user_passes_test(is_distributor, login_url='distributors:login')
def leads(request):
    distributor = request.user
    
    # In PHP:
    # $leads = DB::table('agent_leads')
    #     ->join('agents', 'agent_leads.agent_id', '=', 'agents.id')
    #     ->where('agents.distributor_id', $distributor->id)
    #     ->select('agent_leads.*', 'agents.fullname as agent_name')
    #     ->orderBy('agent_leads.created_at', 'desc')
    #     ->paginate(15);
    from apps.admin_panel.models import User as LaravelUser
    l_user = LaravelUser.objects.filter(email=request.user.email).first()
    distributor_id = l_user.id if l_user else request.user.id
    
    queryset = AgentLead.objects.filter(agent__distributor_id=distributor_id).select_related('agent').order_by('-created_at')
    
    paginator = Paginator(queryset, 15)
    page_number = request.GET.get('page')
    leads_page = paginator.get_page(page_number)
    
    context = {
        'leads': leads_page
    }
    return render(request, 'distributors/leads.html', context)
