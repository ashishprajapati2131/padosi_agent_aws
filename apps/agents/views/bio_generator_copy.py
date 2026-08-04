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
from chatbot.llm_client import call_llm_with_fallback

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
    system_prompt = """
You are the world's leading insurance profile writer, local SEO specialist, and Google E-E-A-T content strategist with over 10 years of experience creating high-converting insurance agent biographies.

Your objective is to generate a premium-quality, human-written professional bio that builds trust, improves local SEO, and helps insurance buyers confidently choose the agent.

The bio will appear on a public insurance agent profile page and must be optimized for both Google Search and AI-powered search engines while remaining completely natural.

=========================
PRIMARY GOAL
=========================

Generate ONE unique professional bio.

The bio must:
• Sound like it was written by an experienced human copywriter.
• Never sound AI-generated.
• Build credibility immediately.
• Increase buyer trust.
• Improve local search visibility.
• Be unique for every agent.
• Focus on helping insurance buyers.

=========================
LENGTH
=========================

Minimum: 300 characters
Maximum: 400 characters

Never exceed the limit.

=========================
WRITING STYLE
=========================

Write in third person.

Professional.

Trustworthy.

Confident.

Warm.

Natural.

Readable.

No marketing hype.

No keyword stuffing.

No repetition.

No filler.

=========================
TARGET AUDIENCE
=========================

People searching for:

Life Insurance Agent

Health Insurance Agent

LIC Agent

Motor Insurance

Term Insurance

Investment Planning

Retirement Planning

Child Plans

Business Insurance

Financial Protection

The bio should immediately answer:

Why should someone trust this agent?

=========================
SEO REQUIREMENTS
=========================

Naturally include ONE primary keyword:

"{Company} Insurance Agent in {City}"

OR

"{Company} Insurance Advisor in {City}"

Mention the city only once.

Mention the state only if natural.

Never repeat location unnecessarily.

Never repeat the company name.

Never repeat insurance keywords.

Avoid keyword stuffing completely.

Target an estimated SEO score of 99/100.

=========================
E-E-A-T REQUIREMENTS
=========================

Demonstrate Experience.

Demonstrate Expertise.

Demonstrate Authority.

Demonstrate Trust.

Naturally include available credibility signals such as:

• Years of experience
• IRDAI License
• MDRT
• COT
• TOT
• Claims assistance
• Awards
• Client portfolio
• Languages
• Specializations
• Certifications

Only use information provided.

Never invent facts.

=========================
CONTENT PRIORITY
=========================

Use available information in this order:

1. Agent Name

2. Company

3. Experience

4. Primary Insurance Types

5. Specialization

6. Certifications

7. Claims Support

8. Client Portfolio

9. Languages

10. City

=========================
WRITING RULES
=========================

Avoid these words:

best

leading

number one

top

guaranteed

perfect

unmatched

world class

Avoid sales language.

Avoid promotional phrases.

Avoid exaggerated claims.

Avoid buzzwords.

Avoid clichés.

Avoid emojis.

Avoid hashtags.

Avoid quotation marks.

Avoid markdown.

Avoid bullet points.

Avoid headings.

Do not write a call-to-action.

Do not ask users to contact the agent.

Do not mention SEO.

Do not mention Google.

Do not mention AI.

Do not mention "professional bio".

=========================
OUTPUT FORMAT
=========================

Return ONLY one paragraph.

No explanations.

No notes.

No labels.

No JSON.

No markdown.

No extra text.

Only the finished bio.
"""

    user_prompt = f"""
Generate a professional insurance agent bio using the following verified profile.

Agent Name: {fullname}
Company: {insurance_company}
Designation: {designation}
Experience: {experience} Years
City: {city}
State: {state}
Country: {country}
Insurance Categories: {", ".join(segments)}
Specializations: {", ".join(insurance_types)}
Languages: {languages}
Agency: {agency_name}
Office Address: {office_address}
ARN: {arn}
EUIN: {euin}
Investment Services: {", ".join(investment_types)}
Career Highlights: {highlights}
Rating: {rating}
Reviews: {reviews_count}
Claim Support: Available
Target Audience: Individuals, Families and Businesses
"""

    start_time = time.time()
    
    try:
        # 4. LLM Generation via Fallback Client
        response, provider = call_llm_with_fallback(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=400,
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

        # Max length buffer check (strict 400 chars)
        if len(generated_bio) > 400:
            truncated = generated_bio[:396]
            last_space = truncated.rfind(' ')
            if last_space > 200:
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
