import datetime
import json
import logging
import time
import re
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.agents.models import Agent, AgentProfile, AgentBioGenerationLog
from chatbot.llm_client import get_groq_client

logger = logging.getLogger(__name__)

@require_POST
def generate_professional_bio(request):
    """
    AI Professional Bio Generator API.
    POST /agent/generate-bio/
    Supports logged-in agent or admin viewing/editing agent profile.
    """
    from apps.admin_panel.views.dashboard import _get_admin_from_session
    admin_id = _get_admin_from_session(request)
    is_admin = bool(admin_id) or (request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser))

    if not is_admin and not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'Authentication required. Please log in.'}, status=401)

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

    # Rate Limiting Check: Removed by request to allow unlimited generations.

    # 2. Gather verified agent information from DB
    fullname = agent.fullname or ""
    designation = getattr(agent, 'profession', '') or "Financial Consultant"
    agency_name = profile.agency_name or ""
    experience = profile.experience_years or getattr(agent, 'experience_range', '') or 0
    languages = profile.formatted_languages or "English, Hindi"
    office_address = profile.office_address or profile.address or agent.agent_pincode or ""
    city = getattr(agent, 'city', '') or (profile.address.split(',')[0].strip() if profile.address else "") or "Ahmedabad"
    state = profile.state or "Gujarat"
    country = "India"

    # Insurance categories & types
    segments = agent.ordered_insurance_segments or []
    insurance_types = []
    if hasattr(agent, 'insuranceSegments'):
        insurance_types = list(agent.insuranceSegments.values_list('segment_type', flat=True))
    
    # Investment details
    arn = profile.arn_number or ""
    euin = profile.euin_number or ""
    investment_types = profile.investment_types or []

    # Career milestones & highlights
    highlights = profile.career_highlights or ""
    rating = agent.average_rating or 5.0
    reviews_count = agent.review_count or 0

    # Determine primary insurance company / agency entity
    insurance_company = agency_name if agency_name else "LIC"

    # Build DB Context
    db_context = {
        "agent_full_name": fullname,
        "designation": designation,
        "agency_name": agency_name,
        "insurance_company": insurance_company,
        "experience_years": f"{experience} years" if experience else "",
        "city": city,
        "state": state,
        "country": country,
        "languages": languages,
        "office_address": office_address,
        "insurance_categories": ", ".join(segments),
        "insurance_types": ", ".join(insurance_types),
        "arn_number": arn,
        "euin_number": euin,
        "investment_services": ", ".join(investment_types),
        "career_highlights": highlights,
        "rating": f"{rating}/5 ({reviews_count} reviews)" if reviews_count else "",
    }

    # Clean context values
    db_context = {k: v for k, v in db_context.items() if v}

    # 3. Construct High-Quality SEO & E-E-A-T LLM Prompt
    system_prompt = (
        "You are an expert SEO Content Writer specializing in Google Search, AI Search (Google AI Overviews, ChatGPT, "
        "Gemini, Perplexity), Local SEO, and E-E-A-T optimization. Your task is to generate a HIGH-QUALITY, human-sounding "
        "SEO profile paragraph for an insurance agent that achieves a 99–100 SEO score. "
        "Return ONLY the final SEO-optimized paragraph. No headings. No bullet points. No markdown. No explanations."
    )

    prompt_context = "\n".join([f"- {k.replace('_', ' ').title()}: {v}" for k, v in db_context.items()])

    prompt_rules = (
        f"\n\nStrict Content & SEO Generation Rules:\n"
        f"1. Target Length: 180 to 250 words total.\n"
        f"2. CTR Opening: Start with an engaging opening sentence (e.g., 'Looking for a trusted Insurance Agent in {city}?...').\n"
        f"3. Primary Keyword: Naturally include 'Insurance Agent in {city}' or 'LIC Agent in {city}'.\n"
        f"4. Local SEO: Naturally mention the location ({city}, {state}, {country}) 2–3 times.\n"
        f"5. Entity Optimization: Connect agent name ({fullname}), insurance company ({insurance_company}), location ({city}), experience ({experience} years), and insurance/investment products naturally.\n"
        f"6. Semantic Keyword Integration: Weave in relevant terms naturally without keyword stuffing (e.g., Life Insurance, Health Insurance, Term Insurance, ULIP, Child Plans, Pension Plans, Retirement Planning, Tax Saving, ELSS, SIP, Mutual Funds, Financial Planning, Claim Assistance, Policy Renewal, Risk Management, Family Protection, Wealth Creation).\n"
        f"7. E-E-A-T Principles: Emphasize years of experience, professional expertise, transparent ethical recommendations, and client-first commitment. Do not fabricate unverified claims.\n"
        f"8. AI Search Optimization: Structure content clearly so AI engines (Google AI Overviews, ChatGPT, Gemini, Perplexity) easily answer: Who is this agent? What services do they provide? Who should contact them? Why choose them? Where do they serve?\n"
        f"9. Readability: Active voice, clear natural phrasing, sentences between 12-20 words, Flesch Reading Ease above 70.\n"
        f"10. Ending: End with a natural closing sentence encouraging users to connect for personalized insurance and investment guidance.\n"
        f"11. Output Constraint: ONLY output the single paragraph of text without markdown, bullet points, titles, or intros."
    )

    full_prompt = "Verified Agent Details:\n" + prompt_context + prompt_rules
    start_time = time.time()
    
    try:
        # 4. LLM Generation via Groq
        client = get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_prompt}
            ],
            temperature=0.7,
            max_tokens=600,
        )
        generation_time = time.time() - start_time
        generated_bio = response.choices[0].message.content.strip()

        # 5. Humanization & Post-processing Pipeline
        # Remove AI prefix patterns
        ai_intros = [
            r"^here is a professional bio[\s\S]*?\n\n",
            r"^here is the generated bio[\s\S]*?\n\n",
            r"^professional bio:?\s*\n+",
            r"^seo profile:?\s*\n+",
        ]
        for pattern in ai_intros:
            generated_bio = re.sub(pattern, "", generated_bio, flags=re.IGNORECASE)

        # Strip emojis and markdown
        generated_bio = generated_bio.replace("*", "").replace("#", "").strip()

        # Clean bullet points if model accidentally added them
        lines = [line.strip() for line in generated_bio.split("\n")]
        cleaned_lines = []
        for line in lines:
            if line.startswith(("-", "*", "•", "1.", "2.", "3.")):
                cleaned_lines.append(line.lstrip("-*•1234567890. "))
            else:
                cleaned_lines.append(line)
        generated_bio = " ".join([p.strip() for p in " ".join(cleaned_lines).split() if p.strip()])

        # Enforce minimum length if needed by padding professionally
        if len(generated_bio) < 500:
            padding_options = [
                f" Committed to delivering professional service, {fullname} focuses on providing trusted financial security and personalized insurance consultation to families across {city}.",
                f" Dedicated to client satisfaction, {fullname} is committed to helping individuals choose clear, secure plans for their long-term requirements.",
                f" By prioritizing transparency and custom solutions, {fullname} assists customers in navigating their investments with complete confidence."
            ]
            for pad_text in padding_options:
                generated_bio += pad_text
                if len(generated_bio) >= 500:
                    break

        # Max length buffer check (allowing 180-250 word full paragraph up to 2500 characters)
        if len(generated_bio) > 2500:
            truncated = generated_bio[:2496]
            last_space = truncated.rfind(' ')
            if last_space > 2000:
                generated_bio = truncated[:last_space] + "..."
            else:
                generated_bio = truncated + "..."

        # Log Success
        tokens = 0
        if response.usage:
            tokens = response.usage.total_tokens

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
        logger.error("AI Bio Generation error: %s", e, exc_info=True)
        # Log Failure
        AgentBioGenerationLog.objects.create(
            agent=agent,
            status='failure',
            error_message=str(e)
        )
        return JsonResponse({
            'status': 'error',
            'message': 'Failed to generate professional bio. Please try again later.'
        }, status=500)
