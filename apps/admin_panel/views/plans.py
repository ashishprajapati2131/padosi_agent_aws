import json
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib import messages
from apps.admin_panel.views.dashboard import _get_admin_from_session
from apps.agents.models import SubscriptionPlan
from apps.admin_panel.models import AdminActivityLog

def plans_index(request):
    admin_id = _get_admin_from_session(request)
    if not admin_id: return redirect('admin_login')
    
    plans = SubscriptionPlan.objects.all().order_by('actual_price')
    return render(request, 'admin/plans/index.html', {'plans': plans})

def plan_create(request):
    admin_id = _get_admin_from_session(request)
    if not admin_id: return redirect('admin_login')
    
    if request.method == 'POST':
        try:
            name = request.POST.get('name')
            html_code = request.POST.get('html_code', '')
            actual_price = request.POST.get('actual_price', 0.0)
            discounted_price = request.POST.get('discounted_price', 0.0)
            is_active = request.POST.get('is_active') == 'on'
            
            show_agent_certificate = request.POST.get('show_agent_certificate') == 'on'
            show_career_timeline = request.POST.get('show_career_timeline') == 'on'
            show_professional_bio = request.POST.get('show_professional_bio') == 'on'
            show_social_media = request.POST.get('show_social_media') == 'on'
            show_new_business_leads = request.POST.get('show_new_business_leads') == 'on'
            show_portfolio = request.POST.get('show_portfolio') == 'on'
            show_claim_support = request.POST.get('show_claim_support') == 'on'
            show_companies = request.POST.get('show_companies') == 'on'
            show_achievement = request.POST.get('show_achievement') == 'on'
            show_lead_status = request.POST.get('show_lead_status') == 'on'
            show_sales_insights = request.POST.get('show_sales_insights') == 'on'
            show_recent_leads = request.POST.get('show_recent_leads') == 'on'
            
            plan = SubscriptionPlan.objects.create(
                name=name,
                html_code=html_code,
                actual_price=actual_price,
                discounted_price=discounted_price,
                is_active=is_active,
                show_agent_certificate=show_agent_certificate,
                show_career_timeline=show_career_timeline,
                show_professional_bio=show_professional_bio,
                show_social_media=show_social_media,
                show_new_business_leads=show_new_business_leads,
                show_portfolio=show_portfolio,
                show_claim_support=show_claim_support,
                show_companies=show_companies,
                show_achievement=show_achievement,
                show_lead_status=show_lead_status,
                show_sales_insights=show_sales_insights,
                show_recent_leads=show_recent_leads
            )
            
            AdminActivityLog.log('Create Plan', 'SubscriptionPlan', plan.id, request=request)
            messages.success(request, f"Plan '{name}' created successfully.")
            return redirect('admin_plans_index')
            
        except Exception as e:
            messages.error(request, f"Error creating plan: {str(e)}")
            
    return render(request, 'admin/plans/form.html', {'title': 'Add New Plan'})

def plan_edit(request, plan_id):
    admin_id = _get_admin_from_session(request)
    if not admin_id: return redirect('admin_login')
    
    plan = get_object_or_404(SubscriptionPlan, id=plan_id)
    
    if request.method == 'POST':
        try:
            plan.name = request.POST.get('name')
            plan.html_code = request.POST.get('html_code', '')
            plan.actual_price = request.POST.get('actual_price', 0.0)
            plan.discounted_price = request.POST.get('discounted_price', 0.0)
            plan.is_active = request.POST.get('is_active') == 'on'
            
            plan.show_agent_certificate = request.POST.get('show_agent_certificate') == 'on'
            plan.show_career_timeline = request.POST.get('show_career_timeline') == 'on'
            plan.show_professional_bio = request.POST.get('show_professional_bio') == 'on'
            plan.show_social_media = request.POST.get('show_social_media') == 'on'
            plan.show_new_business_leads = request.POST.get('show_new_business_leads') == 'on'
            plan.show_portfolio = request.POST.get('show_portfolio') == 'on'
            plan.show_claim_support = request.POST.get('show_claim_support') == 'on'
            plan.show_companies = request.POST.get('show_companies') == 'on'
            plan.show_achievement = request.POST.get('show_achievement') == 'on'
            plan.show_lead_status = request.POST.get('show_lead_status') == 'on'
            plan.show_sales_insights = request.POST.get('show_sales_insights') == 'on'
            plan.show_recent_leads = request.POST.get('show_recent_leads') == 'on'
            
            plan.save()
            
            AdminActivityLog.log('Update Plan', 'SubscriptionPlan', plan.id, request=request)
            messages.success(request, f"Plan '{plan.name}' updated successfully.")
            return redirect('admin_plans_index')
            
        except Exception as e:
            messages.error(request, f"Error updating plan: {str(e)}")
            
    return render(request, 'admin/plans/form.html', {'plan': plan, 'title': 'Edit Plan'})

def plan_delete(request):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=401)
        
    if request.method == 'POST':
        plan_id = request.POST.get('id')
        if not plan_id and request.content_type == 'application/json':
            try:
                data = json.loads(request.body)
                plan_id = data.get('id')
            except Exception:
                pass
                
        if not plan_id:
            return JsonResponse({'success': False, 'message': 'Plan ID is required'}, status=400)
            
        try:
            plan = get_object_or_404(SubscriptionPlan, id=plan_id)
            name = plan.name
            plan.delete()
            AdminActivityLog.log('Delete Plan', 'SubscriptionPlan', plan_id, request=request)
            return JsonResponse({'success': True, 'message': f"Plan '{name}' deleted successfully."})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=500)
            
    return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=405)
