"""Public homepage view and its JSON-LD / reviews helpers."""
from django.shortcuts import render
import re
import logging
import json
from apps.home.services.homepage import build_homepage_cms_context
from django.contrib.staticfiles.storage import staticfiles_storage
from apps.home.services.avatar_thumbs import small_avatar_url
from django.db.models import Q
from django.core.cache import cache

# Keep the original logger name so log lines/filters are unchanged.
logger = logging.getLogger('apps.home.views.pages')


def _reviews_json_for_script(reviews):
    """Serialise testimonials for `var reviewsData = {{ reviews_json|safe }}`.

    The homepage JS concatenates these fields into innerHTML, and anonymous
    reviews are auto-approved, so every string is HTML-escaped here (safe in
    both text and quoted-attribute positions) — this was stored XSS on the
    public homepage. `</` is also neutralised so a value can never close the
    surrounding <script> element.
    """
    import html as _html

    safe_reviews = []
    for review in reviews or []:
        if not isinstance(review, dict):
            continue
        safe_reviews.append({
            key: _html.escape(value, quote=True) if isinstance(value, str) else value
            for key, value in review.items()
        })
    return json.dumps(safe_reviews).replace('</', '<\\/')


def _organization_schema(request):
    """Organization + WebSite JSON-LD for the homepage. Only verifiable fields:
    the footer phone/address defaults are placeholders, so they are left out."""
    from apps.agents.services.og_urls import get_public_site_base
    from apps.home.context_processors import footer_settings

    base = get_public_site_base(request)
    footer = footer_settings(request)['footer_settings']
    name = footer.get('site_name') or 'PadosiAgent'
    org = {
        '@type': 'Organization',
        '@id': f'{base}/#organization',
        'name': name,
        'url': f'{base}/',
        'logo': base + staticfiles_storage.url('img/padosi-agent-logo-new.png'),
        'description': 'Hyperlocal platform to find verified insurance agents near you in India.',
    }
    same_as = [u for u in footer.get('social_links', {}).values() if str(u).startswith('https://')]
    if same_as:
        org['sameAs'] = same_as
    return {
        '@context': 'https://schema.org',
        '@graph': [
            org,
            {
                '@type': 'WebSite',
                '@id': f'{base}/#website',
                'url': f'{base}/',
                'name': name,
                'publisher': {'@id': f'{base}/#organization'},
            },
        ],
    }


def home(request):
    cms = build_homepage_cms_context()
    settings = cms['settings']

    # Testimonials: admin custom list wins; otherwise approved reviews (cached).
    reviews = cms.get('custom_reviews') or []
    if not reviews:
        cached_reviews = cache.get('homepage_reviews')
        if cached_reviews and isinstance(cached_reviews, list):
            # Only trust cache if reviews carry the validated agent_id structure
            if all(isinstance(r, dict) and 'agent_id' in r for r in cached_reviews):
                reviews = cached_reviews
    if not reviews:
        from apps.agents.models import AgentReview
        db_reviews = (
            AgentReview.objects.filter(
                is_approved=True,
                agent__isnull=False,
                agent__status='active',
                agent__is_blacklisted=False,
            )
            .exclude(agent__is_account_active=False)
            .filter(
                Q(agent__profile__isnull=True)
                | (
                    Q(agent__profile__is_profile_visible=True)
                    & Q(agent__profile__show_reviews=True)
                )
            )
            .exclude(agent__email__iendswith='@paldi-test.invalid')
            .select_related('agent', 'agent__profile')
            .order_by('-created_at')[:100]
        )

        agent_counts = {}
        final_reviews = []
        backfill_reviews = []

        for rev in db_reviews:
            agent = rev.agent
            if not agent or agent.status != 'active' or agent.is_blacklisted:
                continue
            if getattr(agent, 'is_account_active', True) is False:
                continue
            if hasattr(agent, 'is_approved_by_admin') and not agent.is_approved_by_admin:
                continue
            profile = agent.get_primary_profile()
            if profile and (not profile.is_profile_visible or not profile.show_reviews):
                continue

            agent_id = rev.agent_id
            if not agent_id:
                continue

            if agent_id not in agent_counts:
                agent_counts[agent_id] = 0
            if agent_counts[agent_id] < 1:
                final_reviews.append(rev)
                agent_counts[agent_id] += 1
            else:
                backfill_reviews.append(rev)

        if len(final_reviews) < 10 and backfill_reviews:
            needed = 10 - len(final_reviews)
            final_reviews.extend(backfill_reviews[:needed])

        final_reviews = final_reviews[:10]

        reviews = []
        for rev in final_reviews:
            agent = rev.agent
            agent_name = agent.fullname if agent else None
            agent_slug = None
            agent_photo = None
            agent_state = 'gj' # Default fallback

            if agent:
                try:
                    profile = agent.get_primary_profile()
                    if profile:
                        agent_slug = profile.slug
                        agent_photo = profile.profile_photo_url
                        agent_state = profile.state_code
                except Exception:
                    pass

            from urllib.parse import quote as _urlquote
            avatar_url = small_avatar_url(agent_photo) if (agent_photo and 'avatar-icon.jpg' not in agent_photo) else f"https://ui-avatars.com/api/?name={_urlquote(rev.reviewer_name or 'User')}&background=0d9488&color=fff&bold=true"

            reviews.append({
                'agent_id': rev.agent_id,
                'name': rev.reviewer_name or 'User',
                'service': f"Client of {agent_name}" if agent_name else "Verified Client",
                'agent_url': f"/{agent_state}/{agent_slug}/" if agent_slug else None,
                'rating': float(rev.rating),
                'comment': rev.review or '',
                'image': avatar_url
            })

        # No placeholder testimonials: unverifiable claims are a YMYL risk.
        # With zero approved reviews the template hides the section.
        if not cms.get('custom_reviews'):
            cache.set('homepage_reviews', reviews, 1800)

    chart_data = [
        {'year': '2020', 'rejection': 12},
        {'year': '2021', 'rejection': 16},
        {'year': '2022', 'rejection': 21},
        {'year': '2023', 'rejection': 27},
        {'year': '2024', 'rejection': 34},
    ]

    raw_heading = settings.hero_heading
    # Clean braces first if any
    cleaned_heading = raw_heading.replace('{', '').replace('}', '')
    def replace_word(match):
        word = match.group(0)
        lower_word = word.lower()
        if 'padosi' in lower_word:
            return f'<span class="pa-heading-highlight">{word}</span>'
        else:
            return f'<span class="pa-heading-trusted">{word}</span>'
    hero_heading_html = re.sub(r'\b(Trusted|Licensed|Licenced|Padosi|Agent)\b', replace_word, cleaned_heading, flags=re.IGNORECASE)

    return render(request, 'public/home.html', {
        'settings': settings,
        'why_cards_zipped': cms['why_cards_zipped'],
        'reviews_json': _reviews_json_for_script(reviews),
        'has_reviews': bool(reviews),
        'org_schema': _organization_schema(request),
        'hide_header': True,
        'trust_badges': cms['trust_badges'],
        'stats_data': cms['stats_data'],
        'product_tiles': cms['product_tiles'],
        'facts_zipped': cms['facts_zipped'],
        'slides_zipped': cms['slides_zipped'],
        'quick_picks': cms['quick_picks'],
        'why_cards': cms['why_cards'],
        'works_steps': cms['works_steps'],
        'chart_data': chart_data,
        'hero_heading_html': hero_heading_html,
    })
