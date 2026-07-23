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

@login_required(login_url='agents:agent_login')
@require_POST
def generate_professional_bio(request):
    """
    AI Professional Bio Generator API.
    POST /api/agent/generate-bio/
    Requires agent login session.
    """
    user = request.user
    agent = Agent.objects.filter(user=user).first()
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

    # Build DB Context
    db_context = {
        "fullname": fullname,
        "designation": designation,
        "agency_name": agency_name,
        "experience_years": f"{experience} years" if experience else "",
        "languages": languages,
        "office_address": office_address,
        "insurance_segments": ", ".join(segments),
        "insurance_types": ", ".join(insurance_types),
        "arn": arn,
        "euin": euin,
        "investment_types": ", ".join(investment_types),
        "career_highlights": highlights,
        "rating": f"{rating}/5 ({reviews_count} reviews)" if reviews_count else "",
    }

    # Clean context values
    db_context = {k: v for k, v in db_context.items() if v}

    # 3. Construct LLM Prompt
    prompt_intro = (
        "You are an expert copywriter specializing in highly engaging, professional, and SEO-optimized bios "
        "for financial and insurance consultants. Your task is to write a custom professional bio using ONLY the "
        "following verified database profile details. Do not invent, fabricate, or assume any facts, achievements, "
        "awards, or licensing details that are not listed below:\n\n"
    )
    
    prompt_context = "\n".join([f"- {k.replace('_', ' ').title()}: {v}" for k, v in db_context.items()])
    
    prompt_rules = (
        "\n\nStrict Output Formatting & Writing Rules:\n"
        "1. Write a naturally human-sounding, professional, and engaging narrative bio in the third-person voice.\n"
        "2. Do not use generic corporate cliches, empty fluff, or AI-like intro phrases (e.g. 'Meet...', 'In the world of...', 'As a trusted advisor...'). Start directly with the agent's name and designation.\n"
        "3. Naturally weave in relevant local and industry SEO keywords based on their specialties (e.g. Health Insurance, Life Insurance, Mutual Funds, SIP, Portfolio Review) without stuffing.\n"
        "4. Highlight the agent's actual experience, agency or company name, core consultation services, service location, and any listed qualifications naturally.\n"
        "5. Keep the bio length strictly between 400 and 500 characters long in total (approximately 65 to 75 words). The output must contain at least 400 characters, and must not exceed 500 characters.\n"
        "6. Do not include bullet points, lists, emojis, markdown heading symbols, or custom formatting. Only output the raw text.\n"
        "7. Ensure the tone is warm, authoritative, and builds client trust, emphasizing financial security and customer consultation.\n"
    )

    full_prompt = prompt_intro + prompt_context + prompt_rules
    start_time = time.time()
    
    try:
        # 4. LLM Generation via Groq
        client = get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a professional profile copywriter. You only output the raw text of the bio without preambles, notes, or intros. Keep the output length strictly between 400 and 500 characters."},
                {"role": "user", "content": full_prompt}
            ],
            temperature=0.7,
            max_tokens=200,
        )
        generation_time = time.time() - start_time
        generated_bio = response.choices[0].message.content.strip()

        # 5. Humanization & Post-processing Pipeline
        # Remove AI prefix patterns
        ai_intros = [
            r"^here is a professional bio[\s\S]*?\n\n",
            r"^here is the generated bio[\s\S]*?\n\n",
            r"^professional bio:?\s*\n+",
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

        # Enforce strict minimum length of 400 characters by padding professionally if too short
        if len(generated_bio) < 400:
            padding_options = [
                f" Committed to delivering professional service, {fullname} focuses on providing trusted financial security and personalized insurance consultation to families.",
                f" Dedicated to client satisfaction, {fullname} is committed to helping individuals choose clear, secure plans for their long-term requirements.",
                f" By prioritizing transparency and custom solutions, {fullname} assists customers in navigating their investments with complete confidence."
            ]
            for pad_text in padding_options:
                if len(generated_bio) + len(pad_text) <= 500:
                    generated_bio += pad_text
                if len(generated_bio) >= 400:
                    break

        # Enforce strict maximum length of 500 characters
        if len(generated_bio) > 500:
            truncated = generated_bio[:496]
            last_space = truncated.rfind(' ')
            if last_space > 400:
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
