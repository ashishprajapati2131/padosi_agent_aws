import logging
import time
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from apps.agents.models import Agent, AgentProfile, AgentBioGenerationLog
from chatbot.llm_client import call_llm_with_fallback

logger = logging.getLogger(__name__)

@require_POST
def generate_professional_bio(request):
    try:
        from apps.admin_panel.views.dashboard import _get_admin_from_session
        admin_id = _get_admin_from_session(request)
        is_admin = bool(admin_id) or (request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser))
        
        agent_id = request.POST.get('agent_id') or request.GET.get('agent_id')
        
        if is_admin and agent_id:
            agent = Agent.objects.filter(id=agent_id).first()
        else:
            agent = Agent.objects.filter(user=request.user).first() if request.user.is_authenticated else None
            if not agent and agent_id and is_admin:
                agent = Agent.objects.filter(id=agent_id).first()

        if not agent:
            return JsonResponse({'status': 'error', 'message': 'Agent profile not found.'}, status=404)

        profile, _ = AgentProfile.objects.get_or_create(agent=agent)

        fullname = agent.fullname or ""
        agency_name = profile.agency_name or "LIC"
        experience = profile.experience_years or getattr(agent, 'experience_range', '') or ""
        city = getattr(agent, 'city', '') or (profile.address.split(',')[0].strip() if profile.address else "") or ""
        languages = profile.formatted_languages or ""
        
        segments = agent.ordered_insurance_segments or []
        insurance_types = []
        if hasattr(agent, 'insuranceSegments'):
            insurance_types = list(agent.insuranceSegments.values_list('segment_type', flat=True))
        
        all_insurance = set(segments + insurance_types)
        insurance_str = ", ".join(all_insurance)

        agent_details = f"""
* Name: {fullname}
* Company: {agency_name}
* Experience: {experience} Years
* City: {city}
* Insurance: {insurance_str}
* Languages: {languages}
* Claim Support: Yes
"""

        system_prompt = """You are an expert insurance copywriter and Local SEO specialist with 10+ years of experience.

Generate a 99/100 SEO-Optimized insurance agent landing page structure using ONLY the verified agent details provided.

Requirements:
- Structure the content as a fully optimized landing page including Technical Metadata and On-Page Content.
- Include a "1. Technical Metadata" section with: SEO Title Tag (Under 60 chars), Meta Description (Under 155 chars), and URL Slug.
- Include a "2. On-Page Content Structure" section with a compelling H1-style heading.
- Include LSI Keywords (e.g., Mediclaim, Family floater, Term insurance, Policy review) naturally.
- Use bullet points to list "Comprehensive Insurance Services Offered".
- Highlight the agent's strongest verified qualifications, experience, specializations, certifications, languages, claim support, and services.
- Incorporate Local Intent Optimization using the agent's city/area.
- Explicitly link their years of expertise to their services to enhance E-E-A-T.
- Add a "Why Choose [Agent Name]?" section and a "Contact [Agent Name] Today" section.
- Output clean text with standard markdown. Do NOT write simple paragraphs."""

        user_prompt = f"""Generate a 99/100 SEO-Optimized insurance agent landing page structure using the verified profile below.

{agent_details}

Ensure the output contains Technical Metadata (Title, Meta Description, URL Slug) and a fully structured On-Page Content section with headings, bullet points, and high-intent LSI keywords. Maximize E-E-A-T and local SEO potential."""

        start_time = time.time()

        response, provider = call_llm_with_fallback(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=1500,
        )
        
        generation_time = time.time() - start_time
        generated_bio = response.choices[0].message.content.strip()

        tokens = response.usage.total_tokens if getattr(response, 'usage', None) else 0

        AgentBioGenerationLog.objects.create(
            agent=agent,
            generation_time=generation_time,
            tokens_used=tokens,
            status='success'
        )

        return JsonResponse({
            'status': 'success',
            'bio': generated_bio
        })

    except Exception as e:
        logger.error(f"Bio generation failed: {str(e)}", exc_info=True)
        if 'agent' in locals() and agent:
            AgentBioGenerationLog.objects.create(
                agent=agent,
                status='failure',
                error_message=str(e)
            )
        return JsonResponse({
            'status': 'error',
            'message': 'Failed to generate professional bio. Please try again later.'
        }, status=500)
