from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from types import SimpleNamespace
from datetime import datetime, timedelta
import json
from apps.home.models.site_setting import SiteSetting
from apps.home.models.faq import Faq
from apps.admin_panel.models.admin_activity_log import AdminActivityLog
from apps.admin_panel.views.dashboard import _get_admin_from_session
from apps.agents.services.feature_unlock import (
    FEATURE_ATTR_MAP,
    FEATURE_LABELS,
    METRIC_CATALOG,
    PLAN_LABELS,
    build_unlock_hints,
    copy_plan_features_config,
    get_unlock_rules,
    normalize_plan_slug,
    remove_plan_only_unlock_rule,
    sanitize_unlock_rules,
    toggle_plan_feature,
    upsert_plan_unlock_rule,
)
from apps.agents.views.dashboard import PlanFeatureProxy


# ─── ABOUT ───────────────────────────────────────────────────────────────────

def about(request):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    about_content = SiteSetting.get_value('about_page_content', {
        'banner_title': 'About Us',
        'banner_subtitle': 'Connecting you with trusted insurance agents in your neighborhood',
        'who_we_are': 'PadosiAgent is a digital-first platform built to simplify how people connect with trusted insurance professionals in their locality.',
        'why_we_exist': 'The insurance ecosystem often faces three common challenges.',
        'what_we_do': 'We provide a platform where customers can discover agents based on location and service segments.',
        'vision': "To build India's most trusted hyperlocal insurance discovery and service platform.",
        'mission': 'Digitally empower insurance agents. Promote transparency and accountability.',
        'commitment': 'PadosiAgent does not replace insurers, brokers, or regulatory authorities.',
    })
    return render(request, 'admin/content/about.html', {'about': about_content})


def update_about(request):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    if request.method == 'POST':
        about_data = {
            'banner_title':    request.POST.get('banner_title', 'About Us'),
            'banner_subtitle': request.POST.get('banner_subtitle', 'Connecting you with trusted insurance agents in your neighborhood'),
            'who_we_are':      request.POST.get('who_we_are', ''),
            'why_we_exist':    request.POST.get('why_we_exist', ''),
            'what_we_do':      request.POST.get('what_we_do', ''),
            'vision':          request.POST.get('vision', ''),
            'mission':         request.POST.get('mission', ''),
            'commitment':      request.POST.get('commitment', ''),
        }
        SiteSetting.set_value('about_page_content', about_data, 'about')
        AdminActivityLog.log('Update about page content', 'SiteSetting', request=request)
        messages.success(request, 'About page updated successfully.')
        return redirect('admin_content_about')

    return redirect('admin_content_about')


# ─── FAQs ────────────────────────────────────────────────────────────────────

def faqs(request):
    """Admin FAQ manager — list all FAQs + page header settings."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    faq_content = SiteSetting.get_value('faq_page_content', {
        'title':    "Got Questions? I've Got Your Answers",
        'subtitle': 'Everything you need to know before finding your PadosiAgent',
    })
    all_faqs = list(Faq.objects.all().order_by('sort_order', 'id'))
    return render(request, 'admin/content/faqs.html', {
        'faq_content':    faq_content,
        'faqs':           all_faqs,
        'active_count':   sum(1 for f in all_faqs if f.is_active),
        'hidden_count':   sum(1 for f in all_faqs if not f.is_active),
        'faq_categories': Faq.CATEGORY_CHOICES,
    })


def faq_settings_update(request):
    """Save FAQ page header (title + subtitle) to site_settings."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    if request.method == 'POST':
        data = {
            'title':    request.POST.get('title', "Got Questions? I've Got Your Answers"),
            'subtitle': request.POST.get('subtitle', 'Everything you need to know before finding your PadosiAgent'),
        }
        SiteSetting.set_value('faq_page_content', data, 'faq')
        AdminActivityLog.log('Update FAQ page header', 'SiteSetting', request=request)
        messages.success(request, 'FAQ page header saved successfully.')
    return redirect('admin_content_faqs')


def faq_store(request):
    """Create a new FAQ entry."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    if request.method == 'POST':
        question   = request.POST.get('question', '').strip()
        answer     = request.POST.get('answer', '').strip()
        category   = request.POST.get('category', 'general')
        sort_order = Faq.objects.count()  # append at end

        if question and answer:
            faq = Faq.objects.create(
                question=question,
                answer=answer,
                category=category,
                sort_order=sort_order,
                is_active=True,
            )
            AdminActivityLog.log(f'Added FAQ #{faq.id}', 'Faq', request=request)
            messages.success(request, 'FAQ added successfully.')
        else:
            messages.error(request, 'Question and Answer are required.')

    return redirect('admin_content_faqs')


def faq_update(request, faq_id):
    """Inline-edit an existing FAQ (question, answer, category)."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    if request.method == 'POST':
        faq_obj  = get_object_or_404(Faq, id=faq_id)
        question = request.POST.get('question', '').strip()
        answer   = request.POST.get('answer', '').strip()
        category = request.POST.get('category', faq_obj.category)

        if question and answer:
            faq_obj.question = question
            faq_obj.answer   = answer
            faq_obj.category = category
            faq_obj.save()
            AdminActivityLog.log(f'Updated FAQ #{faq_id}', 'Faq', request=request)
            messages.success(request, 'FAQ updated successfully.')
        else:
            messages.error(request, 'Question and Answer are required.')

    return redirect('admin_content_faqs')


def faq_toggle(request):
    """Toggle is_active via AJAX — returns JSON {success, is_active}."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False}, status=401)

    if request.method == 'POST':
        faq_id         = request.POST.get('id')
        current_status = request.POST.get('current_status') == 'true'
        faq_obj = get_object_or_404(Faq, id=faq_id)
        faq_obj.is_active = not current_status
        faq_obj.save()
        AdminActivityLog.log(f'Toggled FAQ #{faq_id} → {"active" if faq_obj.is_active else "hidden"}', 'Faq', request=request)
        return JsonResponse({'success': True, 'is_active': faq_obj.is_active})
    return JsonResponse({'success': False}, status=400)


# ─── CONTACT ─────────────────────────────────────────────────────────────────

def contact(request):
    """Admin Contact page editor — banner title + section text."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    contact_content = SiteSetting.get_value('contact_page_content', {
        'banner_title':    'Contact Us',
        'section_title':   'Secure Your Family Future With us.',
        'section_subtitle': "Have questions or need assistance? Reach out to us today for expert guidance on securing your family's future.",
    })
    return render(request, 'admin/content/contact.html', {'contact': contact_content})


def update_contact(request):
    """Save contact page content to site_settings."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    if request.method == 'POST':
        data = {
            'banner_title':    request.POST.get('banner_title', 'Contact Us'),
            'section_title':   request.POST.get('section_title', ''),
            'section_subtitle': request.POST.get('section_subtitle', ''),
        }
        SiteSetting.set_value('contact_page_content', data, 'contact')
        AdminActivityLog.log('Update contact page content', 'SiteSetting', request=request)
        messages.success(request, 'Contact page content saved successfully.')
        return redirect('admin_content_contact')

    return redirect('admin_content_contact')


# ─── BANNER SLIDES ────────────────────────────────────────────────────────────

_DEFAULT_BANNERS = [
    {
        'title': 'Buy/Port/Renew Insurance',
        'subtitle': 'Find your trusted local PadosiAgent',
        'cta_text': 'Find Your PadosiAgent',
        'cta_link': '/find-agents?ServiceType=New%20Policy&openFilter=1',
        'bg_class': 'banner-new-policy',
        'visible': True,
    },
    {
        'title': 'Claim Assistance',
        'subtitle': 'Need help with your insurance claim?',
        'cta_text': 'Find Claims Expert',
        'cta_link': '/find-agents?ServiceType=Claim%20Assistance&openFilter=1',
        'bg_class': 'banner-claim-assistance',
        'visible': True,
    },
    {
        'title': 'Review My Policy',
        'subtitle': "Unsure if you're covered?",
        'cta_text': 'Find Insurance Expert',
        'cta_link': '/find-agents?ServiceType=Policy%20Review&openFilter=1',
        'bg_class': 'banner-policy-review',
        'visible': True,
    },
]


def banners(request):
    """Admin Banner Slides editor — reads/writes homepage_banners in site_settings."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    banner_list = SiteSetting.get_value('homepage_banners', _DEFAULT_BANNERS)
    # Ensure each slide has all expected keys (safe defaults)
    for slide in banner_list:
        slide.setdefault('title', '')
        slide.setdefault('subtitle', '')
        slide.setdefault('cta_text', '')
        slide.setdefault('cta_link', '')
        slide.setdefault('bg_class', '')
        slide.setdefault('visible', True)

    return render(request, 'admin/content/banners.html', {'banners': banner_list})


def update_banners(request):
    """Save banner slides submitted from the banners editor form."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    if request.method == 'POST':
        titles     = request.POST.getlist('title[]')
        subtitles  = request.POST.getlist('subtitle[]')
        cta_texts  = request.POST.getlist('cta_text[]')
        cta_links  = request.POST.getlist('cta_link[]')
        bg_classes = request.POST.getlist('bg_class[]')

        banner_list = []
        for i, title in enumerate(titles):
            # visible[i] checkbox — present means True, absent means False
            visible_key = f'visible[{i}]'
            banner_list.append({
                'title':    title,
                'subtitle': subtitles[i] if i < len(subtitles) else '',
                'cta_text': cta_texts[i] if i < len(cta_texts) else '',
                'cta_link': cta_links[i] if i < len(cta_links) else '',
                'bg_class': bg_classes[i] if i < len(bg_classes) else '',
                'visible':  visible_key in request.POST,
            })

        SiteSetting.set_value('homepage_banners', banner_list, 'homepage')
        AdminActivityLog.log('Updated homepage banner slides', 'SiteSetting', request=request)
        messages.success(request, 'Banner slides updated successfully.')

    return redirect('admin_content_banners')


# ─── PLANS & PRICING ──────────────────────────────────────────────────────────

_DEFAULT_PRICING = {
    'starter': {
        'name': "Starter's Plan",
        'full_price': 2359,
        'promo_price': 589,
        'description': 'Perfect for New Agents',
        'badge': 'STANDARD',
    },
    'professional': {
        'name': "Professional's Plan",
        'full_price': 8258,
        'promo_price': 2359,
        'description': 'For Established Professionals',
        'badge': 'RECOMMENDED',
    },
    'promo_discount_label': 'Partner Promo Applied! Once in a lifetime offer!',
    'standard_label': 'Get started with our standard partner plans',
}


def plans(request):
    """Admin Plans & Pricing editor — reads/writes pricing_config in site_settings."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    pricing = SiteSetting.get_value('pricing_config', _DEFAULT_PRICING)
    # Ensure nested dicts exist with defaults
    pricing.setdefault('starter', _DEFAULT_PRICING['starter'])
    pricing.setdefault('professional', _DEFAULT_PRICING['professional'])
    pricing.setdefault('promo_discount_label', _DEFAULT_PRICING['promo_discount_label'])
    pricing.setdefault('standard_label', _DEFAULT_PRICING['standard_label'])
    
    exclusive_config = SiteSetting.get_value('exclusive_plan_config', {
        'is_active': False,
        'name': 'Exclusive Partner Plan',
        'base_price': 8258,
        'discounted_price': 1000,
        'scratch_threshold_percent': 40,
        'gift_title': 'Surprise! Special Plan Unlocked!',
        'gift_subtitle': 'Follow our social handles to reveal your secret discounted price.',
        'discount_rule': 'ALL_LINKS',
        'required_follow_count': 1,
        'emoji_main': '🎁',
        'emoji_top_left': '🎊',
        'emoji_top_right': '✨',
        'emoji_bottom_left': '🎉',
        'title_prefix': 'Surprise!',
        'title_main': 'Exclusive Plan',
        'title_suffix': 'Unlocked!',
        'old_price': 1999,
        'total_seats': 1000,
        'base_claimed_seats': 964,
        'urgency_line_1': '🔥 Hurry! Offer valid only for the first {total_seats} users!',
        'urgency_line_2': '🔥 <span style="color: #ef4444;">{claimed_seats}/{total_seats}</span> Claimed – <span style="color: #ef4444;">Only {spots_left} Spots Left!</span>',
        'before_discount_val': '85%',
        'after_discount_val': '95%',
        'discount_text_label': 'OFF',
        'extra_discount_msg': 'Extra Follower Discount Applied!',
        'features_header': "What You'll Get",
        'social_header': 'Follow on',
        'checkout_btn_text': 'Claim Offer',
        'social_links': [],
        'premium_features': [],
        'follow_tiers': [],
    })

    plan_features_config = SiteSetting.get_value('plan_features_config', {
        'free_trial': ['dashboard_stats', 'edit_profile'],
        'starter': ['dashboard_stats', 'edit_profile', 'lead_management'],
        'professional': ['dashboard_stats', 'edit_profile', 'lead_management', 'sales_insights', 'manage_portfolio', 'upload_achievements', 'view_reviews', 'public_profile'],
        'exclusive': ['dashboard_stats', 'edit_profile', 'lead_management', 'sales_insights']
    })

    available_features = [
        ('dashboard_stats', 'Dashboard Performance & Stats'),
        ('lead_management', 'Lead Management & Recent Leads'),
        ('sales_insights', 'Sales Insights Widget'),
        ('rank_boost_tips', 'Rank Boost Tips Modal'),
        ('view_public_profile', 'View Public Profile Button'),
        ('edit_profile', 'Edit Profile (Full Access)'),
        ('edit_profile_basic', '— Edit Profile: Basic Details'),
        ('edit_profile_professional', '— Edit Profile: Professional'),
        ('edit_profile_portfolio', '— Edit Profile: Product Portfolio'),
        ('edit_profile_additional', '— Edit Profile: Additional Details'),
        ('manage_portfolio', 'Product Portfolio / Services'),
        ('upload_achievements', 'Gallery / Achievement Photos'),
        ('view_reviews', 'Review Management'),
        ('public_profile', 'Public Profile Customization'),
        ('agent_directory_visibility', 'Listed in Find Agents Directory'),
        ('receive_leads', 'Eligible to Receive New Leads'),
        ('premium_support', 'Premium Priority Support'),
    ]

    legacy_features = [
        ('edit_profile_certifications', 'Agent Certificate'),
        ('edit_profile_career_timeline', 'Career Timeline'),
        ('edit_profile_professional_bio', 'Professional Bio'),
        ('edit_profile_social_media', 'Social Media'),
        ('edit_profile_claim_support', 'Claim Support'),
        ('edit_profile_companies', 'Companies'),
        ('legacy_lead_status', 'Lead Status'),
    ]

    unlock_rules = get_unlock_rules()
    unlock_rule_features = list(available_features) + list(legacy_features)
    unlock_plan_slugs = [
        ('free_trial', 'Free Trial / Expired'),
        ('starter', 'Starter'),
        ('professional', 'Professional'),
        ('exclusive', 'Exclusive'),
    ]
    unlock_builder = {
        'rules': unlock_rules,
        'features': [{'key': k, 'label': l} for k, l in unlock_rule_features],
        'metrics': {
            key: {
                'label': spec['label'],
                'type': spec['type'],
                'operators': list(spec['operators']),
                'widget': spec['widget'],
                'default_op': spec['default_op'],
            }
            for key, spec in METRIC_CATALOG.items()
        },
        'plans': [{'key': k, 'label': l} for k, l in unlock_plan_slugs],
        'opLabels': {'gte': '≥', 'gt': '>', 'lte': '≤', 'lt': '<', 'eq': '=', 'neq': '≠'},
        'segments': [
            {'key': 'health', 'label': 'Health'},
            {'key': 'life', 'label': 'Life'},
            {'key': 'motor', 'label': 'Motor'},
            {'key': 'sme', 'label': 'SME'},
        ],
    }

    return render(request, 'admin/content/plans.html', {
        'pricing': pricing,
        'exclusive_config': exclusive_config,
        'features_config': plan_features_config,
        'available_features': available_features,
        'legacy_features': legacy_features,
        'unlock_rules': unlock_rules,
        'unlock_rule_features': unlock_rule_features,
        'unlock_metric_catalog': METRIC_CATALOG,
        'unlock_plan_slugs': unlock_plan_slugs,
        'unlock_builder': unlock_builder,
    })


def update_plans(request):
    """Save plans & pricing config submitted from the plans editor form."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    if request.method == 'POST':
        pricing = {
            'starter': {
                'name':        request.POST.get('starter_name', "Starter's Plan"),
                'full_price':  int(request.POST.get('starter_full_price', 2359) or 2359),
                'promo_price': int(request.POST.get('starter_promo_price', 589) or 589),
                'description': request.POST.get('starter_description', 'Perfect for New Agents'),
                'badge':       request.POST.get('starter_badge', 'STANDARD'),
            },
            'professional': {
                'name':        request.POST.get('professional_name', "Professional's Plan"),
                'full_price':  int(request.POST.get('professional_full_price', 8258) or 8258),
                'promo_price': int(request.POST.get('professional_promo_price', 2359) or 2359),
                'description': request.POST.get('professional_description', 'For Established Professionals'),
                'badge':       request.POST.get('professional_badge', 'RECOMMENDED'),
            },
            'promo_discount_label': request.POST.get('promo_discount_label', 'Partner Promo Applied! Once in a lifetime offer!'),
            'standard_label':       request.POST.get('standard_label', 'Get started with our standard partner plans'),
        }

        # Keep SiteSetting for legacy texts (promo labels)
        SiteSetting.set_value('pricing_config', pricing, 'pricing')
        
        # Save directly to SubscriptionPlan models
        from apps.agents.models import SubscriptionPlan
        for slug in ['starter', 'professional']:
            plan, _ = SubscriptionPlan.objects.get_or_create(slug=slug, defaults={'name': slug.title()})
            plan.name = pricing[slug]['name']
            plan.description = pricing[slug]['description']
            plan.actual_price = pricing[slug]['full_price']
            plan.discounted_price = pricing[slug]['promo_price']
            plan.badge_text = pricing[slug]['badge']
            plan.save()

        AdminActivityLog.log('Updated agent pricing plans', 'SiteSetting', request=request)
        messages.success(request, 'Pricing configuration updated successfully.')

    return redirect('admin_content_plans')


def update_exclusive_config(request):
    """Save exclusive plan config."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')
    
    if request.method == 'POST':
        # Parse dynamic social links
        social_platforms = request.POST.getlist('social_platform[]')
        social_urls = request.POST.getlist('social_url[]')
        social_icons = request.POST.getlist('social_icon[]')
        social_links = []
        for i in range(len(social_platforms)):
            social_links.append({
                'platform': social_platforms[i],
                'url': social_urls[i] if i < len(social_urls) else '',
                'icon': social_icons[i] if i < len(social_icons) else '',
            })
            
        # Parse dynamic premium features
        pf_names = request.POST.getlist('pf_name[]')
        pf_icons = request.POST.getlist('pf_icon[]')
        pf_colors = request.POST.getlist('pf_color[]')
        pf_bg_colors = request.POST.getlist('pf_bg_color[]')
        premium_features = []
        for i in range(len(pf_names)):
            premium_features.append({
                'name': pf_names[i],
                'icon': pf_icons[i] if i < len(pf_icons) else '',
                'color': pf_colors[i] if i < len(pf_colors) else '#000000',
                'bg_color': pf_bg_colors[i] if i < len(pf_bg_colors) else '#ffffff',
            })

        # Parse dynamic follow tiers
        tier_follows_list = request.POST.getlist('tier_follows[]')
        tier_prices_list = request.POST.getlist('tier_prices[]')
        follow_tiers = []
        for i in range(len(tier_follows_list)):
            try:
                f_count = int(tier_follows_list[i])
                f_price = int(tier_prices_list[i])
                follow_tiers.append({
                    'follows': f_count,
                    'price': f_price
                })
            except ValueError:
                pass
        
        # Sort follow_tiers descending by follows so we can easily pick the highest tier reached
        follow_tiers.sort(key=lambda x: x['follows'], reverse=True)

        config = {
            'is_active': request.POST.get('exc_is_active') == 'on',
            'name': request.POST.get('exclusive_name', 'Exclusive Plan'),
            'base_price': int(request.POST.get('exclusive_base_price', 199) or 199),
            'discounted_price': int(request.POST.get('exclusive_discounted_price', 99) or 99),
            'scratch_threshold_percent': int(request.POST.get('scratch_threshold_percent', 40) or 40),
            'gift_title': request.POST.get('gift_title', 'Surprise! Special Plan Unlocked!'),
            'gift_subtitle': request.POST.get('gift_subtitle', 'Follow our social handles to reveal your secret discounted price.'),
            'discount_rule': request.POST.get('discount_rule', 'ALL_LINKS'),
            'required_follow_count': int(request.POST.get('required_follow_count', 1) or 1),
            'emoji_main': request.POST.get('emoji_main', '🎁'),
            'emoji_top_left': request.POST.get('emoji_top_left', '🎊'),
            'emoji_top_right': request.POST.get('emoji_top_right', '✨'),
            'emoji_bottom_left': request.POST.get('emoji_bottom_left', '🎉'),
            'title_prefix': request.POST.get('title_prefix', 'Surprise!'),
            'title_main': request.POST.get('title_main', 'Exclusive Plan'),
            'title_suffix': request.POST.get('title_suffix', 'Unlocked!'),
            'old_price': int(request.POST.get('old_price', 1999) or 1999),
            'total_seats': int(request.POST.get('total_seats', 1000) or 1000),
            'base_claimed_seats': int(request.POST.get('base_claimed_seats', 964) or 964),
            'urgency_line_1': request.POST.get('urgency_line_1', '🔥 Hurry! Offer valid only for the first {total_seats} users!'),
            'urgency_line_2': request.POST.get('urgency_line_2', '🔥 <span style="color: #ef4444;">{claimed_seats}/{total_seats}</span> Claimed – <span style="color: #ef4444;">Only {spots_left} Spots Left!</span>'),
            'before_discount_val': request.POST.get('before_discount_val', '85%'),
            'after_discount_val': request.POST.get('after_discount_val', '95%'),
            'discount_text_label': request.POST.get('discount_text_label', 'OFF'),
            'extra_discount_msg': request.POST.get('extra_discount_msg', 'Extra Follower Discount Applied!'),
            'features_header': request.POST.get('features_header', 'What You\'ll Get'),
            'social_header': request.POST.get('social_header', 'Follow on'),
            'checkout_btn_text': request.POST.get('checkout_btn_text', 'BUY'),
            
            # Advanced Text & Badge Labels
            'plan_badge': request.POST.get('plan_badge', '👑'),
            'badge_text': request.POST.get('badge_text', 'Top Pick!'),
            'ribbon_text': request.POST.get('ribbon_text', 'Exclusive Deal'),
            'ribbon_color': request.POST.get('ribbon_color', '#8A2BE2'),
            'price_suffix': request.POST.get('price_suffix', '/mo'),
            'total_value_amount': request.POST.get('total_value_amount', 15000),
            'savings_text': request.POST.get('savings_text', '🔥 Save 80% with this super exclusive secret deal!'),
            'old_price_tooltip': request.POST.get('old_price_tooltip', 'Actual market value of all these premium services combined.'),
            'strikeout_price': request.POST.get('strikeout_price', 15000),
            'discount_amount_label': request.POST.get('discount_amount_label', '14801'),
            
            # Action Button Setup
            'locked_btn_text': request.POST.get('locked_btn_text', 'LOCKED'),
            'locked_reason_text': request.POST.get('locked_reason_text', 'Follow Social Media to Unlock'),
            
            # Locked Screen Instructions
            'locked_heading': request.POST.get('locked_heading', 'Please Follow Us First'),
            'locked_desc': request.POST.get('locked_desc', 'Please Follow'),
            
            'social_links': social_links,
            'premium_features': premium_features,
            'follow_tiers': follow_tiers,
        }
        SiteSetting.set_value('exclusive_plan_config', config, 'pricing')
        
        # Save directly to SubscriptionPlan model
        from apps.agents.models import SubscriptionPlan
        plan, _ = SubscriptionPlan.objects.get_or_create(slug='exclusive', defaults={'name': 'Exclusive Plan'})
        plan.name = config['name']
        plan.actual_price = config['strikeout_price']
        plan.discounted_price = config['base_price']
        plan.description = config['gift_title']
        plan.badge_text = config['badge_text']
        plan.save()

        AdminActivityLog.log('Updated exclusive gamified plan', 'SiteSetting', request=request)
        messages.success(request, 'Exclusive Gamified Plan updated successfully.')
        
    return redirect('admin_content_plans')


def update_plan_features(request):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    if request.method == 'POST':
        config = {
            'free_trial': request.POST.getlist('features_free_trial[]'),
            'starter': request.POST.getlist('features_starter[]'),
            'professional': request.POST.getlist('features_professional[]'),
            'exclusive': request.POST.getlist('features_exclusive[]'),
        }
        
        SiteSetting.set_value('plan_features_config', config, 'pricing')
        
        # Save directly to SubscriptionPlan models
        from apps.agents.models import SubscriptionPlan
        from apps.agents.services.feature_unlock import FEATURE_ATTR_MAP
        for slug, plan_features in config.items():
            plan, _ = SubscriptionPlan.objects.get_or_create(slug=slug, defaults={'name': slug.title()})
            # Reset all features
            for f in plan._meta.get_fields():
                if f.get_internal_type() == 'BooleanField' and (f.name.startswith('show_') or f.name.startswith('is_') or f.name.startswith('premium_')):
                    setattr(plan, f.name, False)
            # Enable selected features
            for feature_key in plan_features:
                if feature_key in FEATURE_ATTR_MAP:
                    for attr in FEATURE_ATTR_MAP[feature_key]:
                        setattr(plan, attr, True)
            plan.save()

        AdminActivityLog.log('Update plan feature access config', 'SiteSetting', request=request)
        messages.success(request, 'Plan Feature Permissions updated successfully.')
        
    return redirect('admin_content_plans')


def update_feature_unlock_rules(request):
    """Save activity unlock rules from the Plans & Pricing editor."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    if request.method == 'POST':
        raw = request.POST.get('unlock_rules_json', '{"rules":[]}')
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            messages.error(request, 'Could not save unlock rules. Please try again.')
            return redirect('admin_content_plans')

        if isinstance(data, list):
            raw_rules = data
        elif isinstance(data, dict):
            raw_rules = data.get('rules') or []
        else:
            raw_rules = []

        rules = sanitize_unlock_rules(raw_rules)
        SiteSetting.set_value('feature_unlock_rules', {'rules': rules}, 'pricing')
        AdminActivityLog.log('Updated activity feature unlock rules', 'SiteSetting', request=request)
        messages.success(request, 'Activity unlock rules updated successfully.')

    return redirect('admin_content_plans')


DEFAULT_PLAN_FEATURES = {
    'free_trial': ['dashboard_stats', 'edit_profile'],
    'starter': ['dashboard_stats', 'edit_profile', 'lead_management'],
    'professional': [
        'dashboard_stats', 'edit_profile', 'lead_management', 'sales_insights',
        'manage_portfolio', 'upload_achievements', 'view_reviews', 'public_profile',
    ],
    'exclusive': ['dashboard_stats', 'edit_profile', 'lead_management', 'sales_insights'],
}


class _EmptyRelated:
    def all(self):
        return []

    def exists(self):
        return False

    def count(self):
        return 0

    def first(self):
        return None

    def filter(self, **kwargs):
        return self

    def values_list(self, *args, **kwargs):
        return []


def _preview_unlock_builder():
    features = [{'key': key, 'label': FEATURE_LABELS.get(key, key)} for key in FEATURE_ATTR_MAP]
    return {
        'features': features,
        'metrics': {
            key: {
                'label': spec['label'],
                'type': spec['type'],
                'operators': list(spec['operators']),
                'widget': spec['widget'],
                'default_op': spec['default_op'],
            }
            for key, spec in METRIC_CATALOG.items()
        },
        'opLabels': {'gte': '≥', 'gt': '>', 'lte': '≤', 'lt': '<', 'eq': '=', 'neq': '≠'},
        'segments': [
            {'key': 'health', 'label': 'Health'},
            {'key': 'life', 'label': 'Life'},
            {'key': 'motor', 'label': 'Motor'},
            {'key': 'sme', 'label': 'SME'},
        ],
    }


def _sample_manage_agent_context(plan_slug):
    """Dummy agent/profile so the real dashboard and edit-profile templates render."""
    now = datetime.now()
    profile = SimpleNamespace(
        display_name='Sample Agent',
        slug='sample-agent',
        city='Unjha',
        profile_photo_path='',
        profile_photo_url='/static/img/avatar-icon.webp',
        address='Sample Area, Unjha, Gujarat',
        languages='Gujarati, Hindi, English',
        whatsapp='9876543210',
        whatsapp_digits='9876543210',
        date_of_birth=None,
        pan_number='',
        license_number='',
        license_valid_till=None,
        irdai_license_doc='',
        amfi_license_doc='',
        arn_number='',
        euin_number='',
        investment_valid_till=None,
        agency_name='Sample Agency',
        office_address='Unjha',
        service_pincode='384285',
        website_url='',
        career_highlights='',
        social_links=SimpleNamespace(
            google_business='', linkedin='', instagram='', facebook='', youtube='',
        ),
        show_experience=True,
        show_claims_stats=True,
        show_client_base=True,
        show_ratings=True,
        show_reviews=True,
        show_certificates=True,
        show_achievements=True,
        show_social_links=True,
        show_languages=True,
        show_gallery=True,
        show_contact_info=True,
        has_pos_license=False,
        investment_types=[],
    )
    performance = SimpleNamespace(
        claims_processed=150,
        claims_settled=140,
        claims_amount=2500000,
        success_rate=93,
        formatted_claims_processed='150',
        formatted_claims_amount='25L',
    )
    agent = SimpleNamespace(
        id=1,
        fullname='Sample Agent',
        display_name='Sample Agent',
        mobile='9876543210',
        email='sample@example.com',
        status='active',
        plan_type=plan_slug,
        experience_range='5-10',
        experience_years=8,
        client_base=120,
        formatted_client_base='120',
        agent_pincode='384285',
        agent_slug='sample-agent',
        review_count=12,
        star_rating_list=['full', 'full', 'full', 'full', 'empty'],
        average_rating=4.2,
        padosi_smart_rank=8,
        calculated_match_percent=80,
        badge='verified',
        agent_city_display='Unjha',
        is_trusted=True,
        is_approved_by_admin=True,
        is_verified_agent=True,
        whatsapp_raw='9876543210',
        distance=0,
        has_distance=False,
        ordered_insurance_segments=['health', 'life'],
        sorted_career_timelines=[],
        insuranceSegments=_EmptyRelated(),
        portfolios=_EmptyRelated(),
        productExpertise=_EmptyRelated(),
        serviceableCities=_EmptyRelated(),
        leads=_EmptyRelated(),
        activeSubscription=None,
        leadPreferences=SimpleNamespace(
            leads_new_business=True,
            portfolio_charging='',
            portfolio_fee=0,
            claims_charging='',
            claims_fee_amount=0,
            claims_percent=0,
        ),
        performanceStats=performance,
        profile=profile,
    )
    recent_leads = [
        SimpleNamespace(
            id=1,
            customer_name='Asha Patel',
            customer_mobile='9000000001',
            customer_email='asha@example.com',
            customer_pincode='384285',
            insurance_type='Health',
            enquiry_requirements='Family floater',
            interaction_type='profile',
            lead_status='new',
            created_at=now - timedelta(hours=3),
        ),
        SimpleNamespace(
            id=2,
            customer_name='Ravi Shah',
            customer_mobile='9000000002',
            customer_email='ravi@example.com',
            customer_pincode='384001',
            insurance_type='Life',
            enquiry_requirements='Term plan',
            interaction_type='whatsapp',
            lead_status='contacted',
            created_at=now - timedelta(days=1),
        ),
    ]
    return {
        'agent': agent,
        'profile': profile,
        'dashboardStats': {
            'conversionRate': 24,
            'monthlyTarget': 60,
            'totalPageViews': 128,
            'contactRequests': 9,
            'monthlyLeads': 4,
            'newLeads': 6,
            'contactedLeads': 3,
            'followUpLeads': 2,
            'closedLeads': 1,
            'totalLeads': 12,
            'activeLeads': 5,
            'monthlyVisits': 86,
        },
        'recentLeads': recent_leads,
        'allLeads': recent_leads,
        'showReferral': False,
        'unreadNotifications': [],
        'unread_notifications_json': '[]',
        'completion': 72,
        'isOnTrial': False,
        'daysLeft': 0,
        'discountPct': 0,
        'starterFull': 2359,
        'starterDisc': 589,
        'profFull': 8258,
        'profDisc': 2359,
        'planName': PLAN_LABELS.get(plan_slug, plan_slug.replace('_', ' ').title()),
        'favorite_ids': set(),
        'fcm_api_key': '',
        'fcm_auth_domain': '',
        'fcm_project_id': '',
        'fcm_storage_bucket': '',
        'fcm_messaging_sender_id': '',
        'fcm_app_id': '',
        'fcm_vapid_key': '',
        'isAdminView': False,
        'base_template': 'admin/base.html',
        'main_cities': ['Ahmedabad', 'Unjha', 'Patan', 'Mehsana'],
        'agent_cities': ['Unjha'],
        'extra_cities': [],
        'years_range': list(range(datetime.now().year, 1979, -1)),
        'months': [
            'January', 'February', 'March', 'April', 'May', 'June',
            'July', 'August', 'September', 'October', 'November', 'December',
        ],
        'active_investment_types': [],
    }


def _manage_agent_common_context(plan_slug):
    features_config = copy_plan_features_config(
        SiteSetting.get_value('plan_features_config', DEFAULT_PLAN_FEATURES) or DEFAULT_PLAN_FEATURES
    )
    enabled = features_config.get(plan_slug) or []
    rules = get_unlock_rules()
    hints = build_unlock_hints(None, plan_slug, metrics={}, rules=rules)
    context = _sample_manage_agent_context(plan_slug)
    context.update({
        'admin_lock_preview': True,
        'preview_plan_slug': plan_slug,
        'preview_plan_label': PLAN_LABELS.get(plan_slug, plan_slug),
        'agent_plan': PlanFeatureProxy(enabled),
        'feature_unlock_hints_json': json.dumps(hints),
        'preview_enabled_features': enabled,
        'preview_enabled_features_json': json.dumps(enabled),
        'preview_unlock_builder': _preview_unlock_builder(),
        'preview_unlock_builder_json': json.dumps(_preview_unlock_builder()),
        'preview_feature_labels_json': json.dumps(FEATURE_LABELS),
        'hide_header': True,
        'hide_footer': True,
    })
    # Let admin_badge_counts keep the real session admin so the sidebar renders.
    context.pop('logged_in_admin', None)
    context.pop('is_super_admin', None)
    context.pop('admin_permissions', None)
    return context, features_config, rules


@ensure_csrf_cookie
def manage_agent_preview(request, plan_slug):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    slug = normalize_plan_slug(plan_slug)
    if slug not in PLAN_SLUGS:
        messages.error(request, 'Unknown plan.')
        return redirect('admin_content_plans')

    tab = (request.GET.get('tab') or 'dashboard').strip()
    if tab not in ('dashboard', 'edit_profile', 'other'):
        tab = 'dashboard'

    context, _, _ = _manage_agent_common_context(slug)
    context['preview_tab'] = tab

    if tab == 'edit_profile':
        template = 'agents/edit_profile.html'
    elif tab == 'other':
        template = 'admin/content/manage_agent_other.html'
    else:
        template = 'agents/dashboard.html'
    return render(request, template, context)


@require_POST
@csrf_protect
def manage_agent_toggle(request, plan_slug):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'ok': False, 'error': 'Unauthorized'}, status=403)

    slug = normalize_plan_slug(plan_slug)
    if slug not in PLAN_SLUGS:
        return JsonResponse({'ok': False, 'error': 'Unknown plan'}, status=400)

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return HttpResponseBadRequest('Invalid JSON')

    feature = (payload.get('feature') or '').strip()
    if feature not in FEATURE_ATTR_MAP:
        return JsonResponse({'ok': False, 'error': 'Unknown feature'}, status=400)

    locked = bool(payload.get('locked'))
    add_condition = bool(payload.get('add_condition'))
    if locked and add_condition:
        trial_rules = upsert_plan_unlock_rule(
            [], slug, feature, payload.get('conditions') or [],
            match='any' if payload.get('match') == 'any' else 'all',
        )
        if not trial_rules:
            return JsonResponse({
                'ok': False,
                'error': 'Add a valid unlock condition (choose a metric and a value).',
            }, status=400)

    features_config = copy_plan_features_config(
        SiteSetting.get_value('plan_features_config', DEFAULT_PLAN_FEATURES) or DEFAULT_PLAN_FEATURES
    )
    new_config = toggle_plan_feature(features_config, slug, feature, locked)
    SiteSetting.set_value('plan_features_config', new_config, 'pricing')

    rules = get_unlock_rules()
    if locked and add_condition:
        match = 'any' if payload.get('match') == 'any' else 'all'
        rules = upsert_plan_unlock_rule(
            rules, slug, feature, payload.get('conditions') or [], match=match,
        )
        SiteSetting.set_value('feature_unlock_rules', {'rules': rules}, 'pricing')
    elif not locked:
        trimmed = remove_plan_only_unlock_rule(rules, slug, feature)
        if trimmed != rules:
            rules = trimmed
            SiteSetting.set_value('feature_unlock_rules', {'rules': rules}, 'pricing')

    try:
        AdminActivityLog.log(
            f"{'Locked' if locked else 'Unlocked'} {feature} on {slug}",
            'SiteSetting',
            request=request,
        )
    except Exception:
        pass
    return JsonResponse({
        'ok': True,
        'plan_slug': slug,
        'feature': feature,
        'locked': locked,
        'enabled_features': new_config.get(slug) or [],
        'rules': rules,
    })
