import json
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib import messages
from django.utils.text import slugify
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
            # Auto-generate slug from plan name so it flows consistently
            # through agent.plan_type, SiteSettings keys, and Manage panel
            slug = slugify(name) if name else ''
            description = request.POST.get('description', '')
            color_theme = request.POST.get('color_theme', 'starter-theme')
            badge_text = request.POST.get('badge_text', '')
            sort_order = int(request.POST.get('sort_order') or 0)
            html_code = request.POST.get('html_code', '')
            actual_price = request.POST.get('actual_price', 0.0)
            discounted_price = request.POST.get('discounted_price', 0.0)
            is_active = request.POST.get('is_active') == 'on'
            
            show_profile_section = request.POST.get('show_profile_section') == 'on'
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
            
            # New Plan-Based Feature Access Control fields
            show_performance_stats = request.POST.get('show_performance_stats') == 'on'
            show_rank_boost_tips = request.POST.get('show_rank_boost_tips') == 'on'
            show_view_public_profile_btn = request.POST.get('show_view_public_profile_btn') == 'on'
            show_edit_profile_full = request.POST.get('show_edit_profile_full') == 'on'
            show_edit_profile_basic = request.POST.get('show_edit_profile_basic') == 'on'
            show_edit_profile_professional = request.POST.get('show_edit_profile_professional') == 'on'
            show_edit_profile_portfolio = request.POST.get('show_edit_profile_portfolio') == 'on'
            show_edit_profile_additional = request.POST.get('show_edit_profile_additional') == 'on'
            show_review_management = request.POST.get('show_review_management') == 'on'
            is_listed_in_directory = request.POST.get('is_listed_in_directory') == 'on'
            premium_priority_support = request.POST.get('premium_priority_support') == 'on'
            
            plan = SubscriptionPlan.objects.create(
                name=name,
                slug=slug,
                description=description,
                color_theme=color_theme,
                badge_text=badge_text,
                sort_order=sort_order,
                html_code=html_code,
                actual_price=actual_price,
                discounted_price=discounted_price,
                is_active=is_active,
                show_profile_section=show_profile_section,
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
                show_recent_leads=show_recent_leads,
                show_performance_stats=show_performance_stats,
                show_rank_boost_tips=show_rank_boost_tips,
                show_view_public_profile_btn=show_view_public_profile_btn,
                show_edit_profile_full=show_edit_profile_full,
                show_edit_profile_basic=show_edit_profile_basic,
                show_edit_profile_professional=show_edit_profile_professional,
                show_edit_profile_portfolio=show_edit_profile_portfolio,
                show_edit_profile_additional=show_edit_profile_additional,
                show_review_management=show_review_management,
                is_listed_in_directory=is_listed_in_directory,
                premium_priority_support=premium_priority_support
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
            # Auto-generate slug from updated name; preserves consistency
            # with SiteSettings keys and agent.plan_type
            plan.slug = slugify(plan.name) if plan.name else plan.slug
            plan.description = request.POST.get('description', '')
            plan.color_theme = request.POST.get('color_theme', 'starter-theme')
            plan.badge_text = request.POST.get('badge_text', '')
            plan.sort_order = int(request.POST.get('sort_order') or 0)
            plan.html_code = request.POST.get('html_code', '')
            plan.actual_price = request.POST.get('actual_price', 0.0)
            plan.discounted_price = request.POST.get('discounted_price', 0.0)
            plan.is_active = request.POST.get('is_active') == 'on'
            
            plan.show_profile_section = request.POST.get('show_profile_section') == 'on'
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
            
            # New Plan-Based Feature Access Control fields
            plan.show_performance_stats = request.POST.get('show_performance_stats') == 'on'
            plan.show_rank_boost_tips = request.POST.get('show_rank_boost_tips') == 'on'
            plan.show_view_public_profile_btn = request.POST.get('show_view_public_profile_btn') == 'on'
            plan.show_edit_profile_full = request.POST.get('show_edit_profile_full') == 'on'
            plan.show_edit_profile_basic = request.POST.get('show_edit_profile_basic') == 'on'
            plan.show_edit_profile_professional = request.POST.get('show_edit_profile_professional') == 'on'
            plan.show_edit_profile_portfolio = request.POST.get('show_edit_profile_portfolio') == 'on'
            plan.show_edit_profile_additional = request.POST.get('show_edit_profile_additional') == 'on'
            plan.show_review_management = request.POST.get('show_review_management') == 'on'
            plan.is_listed_in_directory = request.POST.get('is_listed_in_directory') == 'on'
            plan.premium_priority_support = request.POST.get('premium_priority_support') == 'on'
            
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
