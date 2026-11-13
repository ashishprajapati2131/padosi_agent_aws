"""SEO city / state / category agent directory pages (/insurance-agents/<city>/...)."""
from django.shortcuts import render
import logging
from apps.home.services.agent_filters import (
    listed_agents_queryset,
)
from django.db.models import Q

# Keep the original logger name so log lines/filters are unchanged.
logger = logging.getLogger('apps.home.views.pages')



# ---------------------------------------------------------------------------
# Area/locality → pincodes mapping for major Indian cities.
# Used by city_agents_directory to resolve hyperlocal area slugs.
# ---------------------------------------------------------------------------
_AREA_PINCODE_MAP = {
    # Ahmedabad localities
    'paldi': ['380007'],
    'satellite': ['380015'],
    'bopal': ['380058'],
    'bodakdev': ['380054'],
    'vastrapur': ['380015'],
    'navrangpura': ['380009'],
    'sg highway': ['382481', '380059'],
    's g highway': ['382481', '380059'],
    'prahlad nagar': ['380015'],
    'thaltej': ['380059'],
    'maninagar': ['380008'],
    'vastral': ['382418'],
    'chandkheda': ['382424'],
    'gota': ['382481'],
    'nikol': ['382350'],
    'naranpura': ['380013'],
    'memnagar': ['380052'],
    'vejalpur': ['380051'],
    'juhapura': ['380055'],
    'isanpur': ['382443'],
    'odhav': ['382415'],
    'naroda': ['382330'],
    'motera': ['380005'],
    'sabarmati': ['380019'],
    'ranip': ['382480'],
    'science city': ['380060'],
    'shilaj': ['380058'],
    'shela': ['382213'],
    'ambli': ['380058'],
    'uvarsad': ['382422'],
    'sanand': ['382110'],
    'ghuma': ['380058'],
    'south bopal': ['380058'],
    'new ranip': ['382480'],
    'krishnanagar': ['382346'],
    'vatva': ['382445'],
    'rakhial': ['380023'],
    'ghodasar': ['380050'],
    'nikol-naroda': ['382350'],
    'new cg road': ['382421'],
    'chharodi': ['382481'],
    'tragad': ['382470'],
    'sola': ['380060'],
    'hebatpur': ['382422'],
    'dhandhuka': ['382460'],
    'dholka': ['382225'],
    'bavla': ['382220'],
    'dehgam': ['382305'],
    'unjha': ['384170'],
    'mehsana': ['384002'],
    'gandhinagar': ['382010', '382021', '382022', '382023', '382024', '382028'],
    'kudasan': ['382421'],
    'adalaj': ['382421'],
    'pethapur': ['382610'],
    # Surat localities
    'adajan': ['395009'],
    'athwa': ['395001'],
    'citylight': ['395007'],
    'vesu': ['395007'],
    'piplod': ['395007'],
    'althan': ['395017'],
    'pal': ['395009'],
    'katargam': ['395004'],
    'udhna': ['394210'],
    'varachha': ['395006'],
    'rander': ['395005'],
    'dumas': ['394550'],
    'sachin': ['394230'],
    'pandesara': ['394221'],
    'bhestan': ['395023'],
    'magdalla': ['395007'],
    'ghod dod road': ['395001'],
    'ghod-dod road': ['395001'],
    'laskana': ['394210'],
    # Rajkot localities
    'kalawad road': ['360005'],
    'gondal road': ['360002'],
    'mavdi': ['360004'],
    'raiya road': ['360007'],
    'university road': ['360005'],
    'bhaktinagar': ['360002'],
    'pedak road': ['360003'],
    'kothariya': ['360003'],
    'aji industrial': ['360003'],
    'metoda': ['360021'],
    # Vadodara localities
    'alkapuri': ['390007'],
    'fatehgunj': ['390002'],
    'productivity road': ['390020'],
    'harni': ['390022'],
    'gorwa': ['390016'],
    'makarpura': ['390014'],
    'karelibaug': ['390018'],
    'waghodia road': ['390019'],
    'subhanpura': ['390023'],
    'vasna': ['390007'],
    'manjalpur': ['390011'],
    'sama': ['390008'],
    # Mumbai localities
    'andheri': ['400058', '400053', '400069'],
    'bandra': ['400050', '400051'],
    'powai': ['400076'],
    'malad': ['400064', '400095'],
    'borivali': ['400066', '400091', '400092'],
    'kandivali': ['400067', '400101'],
    'goregaon': ['400062', '400063'],
    'jogeshwari': ['400060'],
    'vile parle': ['400056', '400057'],
    'santacruz': ['400054', '400055'],
    'kurla': ['400070', '400024'],
    'ghatkopar': ['400077', '400086'],
    'mulund': ['400080', '400081'],
    'thane': ['400601', '400602', '400603'],
    'navi mumbai': ['400614', '400703', '400705'],
    # Bangalore localities
    'koramangala': ['560034'],
    'indiranagar': ['560038'],
    'whitefield': ['560066'],
    'hsr layout': ['560102'],
    'marathahalli': ['560037'],
    'electronic city': ['560100'],
    'jp nagar': ['560078'],
    'jayanagar': ['560041'],
    'btm layout': ['560076'],
    'yelahanka': ['560064'],
    # Pune localities
    'baner': ['411045'],
    'kothrud': ['411038'],
    'viman nagar': ['411014'],
    'hinjewadi': ['411057'],
    'wakad': ['411057'],
    'kharadi': ['411014'],
    'hadapsar': ['411028'],
    'aundh': ['411007'],
    'deccan': ['411004'],
    'pimpri chinchwad': ['411017', '411018', '411019'],
}


MIN_INDEXABLE_CITY_AGENTS = 1
# Agent-typed "cities" that are not places: pages stay up (profile breadcrumbs link here) but are noindex and kept out of the sitemap.
JUNK_CITY_SLUGS = frozenset({'all-pune', 'all-world', 'and-all-over-world', 'pan-india'})


def _resolve_area_to_pincodes(area_name_lower):
    """Return a list of pincodes for a known locality/area name, else empty list."""
    area = area_name_lower.strip()
    if area in _AREA_PINCODE_MAP:
        return _AREA_PINCODE_MAP[area]
    # Partial match: check if any key starts with / contains the area
    for key, pins in _AREA_PINCODE_MAP.items():
        if area in key or key in area:
            return pins
    return []


# /insurance-agents/<city>/<category>/ pages: slug → segment_type in insuranceSegments.
CITY_CATEGORIES = {
    'health-insurance': {
        'label': 'Health Insurance',
        'segment': 'health',
        'keywords': 'health insurance agent in {city}, mediclaim agent in {city}, health insurance advisor near me {city}, family floater health insurance {city}',
        'intro': (
            'Find verified health insurance and mediclaim agents in {city}. A local advisor helps you compare '
            'family floater, senior citizen and top-up plans, checks which network hospitals in {city} offer '
            'cashless treatment, and stays by your side when you file a claim.'
        ),
        'faqs': [
            ('Does buying health insurance through an agent in {city} cost more?',
             'No. The premium is fixed by the insurance company and is the same whether you buy online or through '
             'an agent. The agent is paid by the insurer, not by you.'),
            ('Can a local agent help with a cashless claim at a hospital in {city}?',
             'Yes. An agent can tell you which hospitals are in your insurer\'s cashless network, help with the '
             'pre-authorisation form and follow up with the insurer or TPA. Final approval is given by the insurer.'),
            ('What should I check before choosing a health insurance plan?',
             'Check the sum insured, waiting periods for pre-existing diseases, room rent limits, co-payment, '
             'the insurer\'s network hospitals near you and its claim settlement record.'),
            ('How do I contact a health insurance agent on PadosiAgent?',
             'Open any agent profile on this page and call or WhatsApp them directly. There is no fee for using PadosiAgent.'),
        ],
    },
    'life-insurance': {
        'label': 'Life Insurance',
        'segment': 'life',
        'keywords': 'life insurance agent in {city}, LIC agent in {city}, LIC agent near me {city}, term insurance advisor {city}',
        'intro': (
            'Find verified life insurance, term insurance and LIC agents in {city}. A local advisor helps you '
            'work out the cover your family needs, compare term, endowment and retirement plans, and supports '
            'your nominee when it is time to claim.'
        ),
        'faqs': [
            ('How do I find a trusted LIC or life insurance agent in {city}?',
             'Compare the verified agents on this page by experience, reviews and the companies they represent, '
             'then call or WhatsApp them directly from their profile.'),
            ('Is term insurance better than an endowment or money-back plan?',
             'Term insurance gives the highest cover for the lowest premium but pays only on death. Endowment and '
             'money-back plans add savings but cost more for the same cover. An agent can help you choose based on your goals.'),
            ('How much life cover should I take?',
             'A common rule of thumb is 10 to 15 times your yearly income, plus any loans. Your agent can work out '
             'a figure based on your family\'s expenses and goals.'),
            ('Does a life insurance agent help my family with the claim?',
             'Yes. A local agent helps the nominee collect documents, fill the claim form and follow up with the insurer.'),
        ],
    },
    'lic-agents': {
        'label': 'LIC',
        # Matched on the insurer name saved in the agent's portfolio (see fastapi_app/utils/companies.py).
        'companies': ['Life Insurance Corporation'],
        'keywords': 'LIC agent in {city}, LIC agent near me {city}, LIC policy advisor {city}, LIC premium payment help {city}, LIC claim assistance {city}',
        'intro': (
            'Find verified LIC agents in {city}. A local LIC advisor helps you choose between term, endowment, '
            'money-back and pension plans, keeps track of premium due dates, revives lapsed policies and supports '
            'your family with maturity and death claims.'
        ),
        'faqs': [
            ('How do I find a genuine LIC agent in {city}?',
             'Every agent on this page represents LIC on their PadosiAgent profile. Check their experience and reviews, '
             'and ask for their LIC agent code before you buy.'),
            ('Can an LIC agent help me revive a lapsed policy?',
             'Yes. An agent can tell you the revival amount, any medical requirements and the forms LIC needs.'),
            ('Does an LIC agent help with maturity and death claims?',
             'Yes. The agent helps you or your nominee collect the documents, submit the claim to the LIC branch and follow it up.'),
            ('Is it free to contact an LIC agent on PadosiAgent?',
             'Yes. Open any agent profile on this page and call or WhatsApp them directly. There is no fee for using PadosiAgent.'),
        ],
    },
    'motor-insurance': {
        'label': 'Car & Bike Insurance',
        'segment': 'motor',
        'keywords': 'car insurance agent in {city}, bike insurance agent in {city}, motor insurance renewal {city}, two wheeler insurance agent near me {city}',
        'intro': (
            'Find verified car and bike insurance agents in {city}. A local advisor helps you renew on time, '
            'pick the right add-ons like zero depreciation, transfer your no-claim bonus and handle the survey '
            'and garage paperwork after an accident.'
        ),
        'faqs': [
            ('Can an agent in {city} renew my expired car or bike insurance?',
             'Yes. If the policy has lapsed the insurer may ask for a vehicle inspection before renewal. A local agent can arrange it.'),
            ('Is third-party insurance enough for my vehicle?',
             'Third-party cover is the legal minimum, but it does not pay for damage to your own vehicle. A '
             'comprehensive policy covers both.'),
            ('What documents do I need for a car insurance claim after an accident?',
             'Usually the policy copy, RC, driving licence, claim form, repair estimate and, for theft or major '
             'accidents, an FIR. Your agent will confirm what your insurer needs.'),
            ('Will I lose my no-claim bonus if I switch insurers?',
             'No. The no-claim bonus belongs to you, not the insurer, and can be transferred when you renew with another company.'),
        ],
    },
    'business-insurance': {
        'label': 'Business Insurance',
        'segment': 'sme',
        'keywords': 'business insurance agent in {city}, SME insurance advisor {city}, shop insurance {city}, group health insurance for employees {city}, fire insurance agent {city}',
        'intro': (
            'Find verified business and SME insurance advisors in {city}. A local advisor helps shops, factories '
            'and offices choose fire, property, liability, cyber and employee group health cover that fits the business.'
        ),
        'faqs': [
            ('What insurance does a small business in {city} need?',
             'Most businesses start with fire and property cover for the premises and stock, plus group health '
             'cover for employees. Liability and cyber cover depend on the type of business.'),
            ('Can an agent arrange group health insurance for my employees?',
             'Yes. Group health (GMC) and group personal accident (GPA) policies can be arranged for teams of any size.'),
            ('Does a business insurance agent help with claims?',
             'Yes. The agent helps with the claim intimation, surveyor visit and documents, and follows up with the insurer.'),
            ('How do I contact a business insurance advisor on PadosiAgent?',
             'Open any advisor profile on this page and call or WhatsApp them directly. There is no fee for using PadosiAgent.'),
        ],
    },
}


# /<service>/<city>/ pages: every listed agent in the city, with service-specific copy.
SERVICE_PAGES = {
    'insurance-claim-assistance': {
        'label': 'Insurance Claim Assistance',
        'keywords': 'insurance claim assistance in {city}, insurance claim support {city}, health insurance claim assistance {city}, car insurance claim assistance {city}, insurance claim advisor near me {city}',
        'intro': (
            'Get help with your insurance claim in {city}. Verified local advisors guide you through health, '
            'life, motor and business insurance claims: what to tell the insurer, which documents to collect, '
            'cashless versus reimbursement, and how to follow up on a delayed or rejected claim.'
        ),
        'faqs': [
            ('Can a local advisor in {city} help if my policy was bought from someone else?',
             'Yes. Many advisors on this page help with claims on any policy. Share your policy details when you '
             'contact them and they will tell you how they can help.'),
            ('What documents are usually needed for a health insurance claim?',
             'Usually the claim form, policy copy, ID proof, hospital bills, discharge summary, doctor\'s '
             'prescriptions and test reports. For reimbursement claims you also need the original bills and a '
             'cancelled cheque. Your insurer may ask for more.'),
            ('What should I do first after a car accident?',
             'Inform your insurer as soon as you can, take photos of the vehicle and the spot, and do not move the '
             'vehicle to a garage before the insurer says so. File an FIR if there is injury, theft or major damage.'),
            ('My claim was rejected. Can an advisor help?',
             'An advisor can read the rejection letter, check it against your policy terms and help you appeal to '
             'the insurer\'s grievance cell. If that fails, you can approach the Insurance Ombudsman.'),
        ],
    },
    'insurance-renewal': {
        'label': 'Insurance Policy Renewal',
        'keywords': 'insurance policy renewal agent {city}, insurance renewal near me {city}, health insurance renewal agent {city}, car insurance renewal {city}, bike insurance renewal agent {city}, insurance policy review {city}',
        'intro': (
            'Renew your health, life, car or bike insurance with a verified local advisor in {city}. An advisor '
            'reviews your current cover before renewal, compares plans, keeps your no-claim bonus and waiting-period '
            'benefits, and reminds you before the next due date.'
        ),
        'faqs': [
            ('What happens if I miss my health insurance renewal date?',
             'Most insurers give a short grace period. If you renew after it ends, the policy may lapse and you can '
             'lose waiting-period credit for pre-existing diseases. Renew before the due date.'),
            ('Can I switch insurers at renewal without losing benefits?',
             'Yes. Health insurance portability lets you carry waiting-period credit to a new insurer, and the motor '
             'no-claim bonus can be transferred. Apply before your current policy expires.'),
            ('Can my bike or car insurance be renewed after it has expired?',
             'Yes, but the insurer may ask for a vehicle inspection, and driving without valid insurance is illegal. '
             'A local advisor can arrange the inspection.'),
            ('Is a policy review before renewal useful?',
             'Yes. Your income, family and vehicle may have changed. A review checks whether your sum insured and '
             'add-ons still fit before you pay the next premium.'),
        ],
    },
}

# /insurance-agents/<state>/ hubs: every listed agent serving a city in that state.
# Live cities mostly have an empty `state`, so a hub also matches known city names and the agent's pincode.
STATE_HUBS = {
    'gujarat': {
        'name': 'Gujarat',
        'pin_prefixes': ('36', '37', '38', '39'),
        'cities': (
            'Ahmedabad', 'Surat', 'Vadodara', 'Rajkot', 'Gandhinagar', 'Bhavnagar', 'Jamnagar', 'Junagadh',
            'Anand', 'Nadiad', 'Bharuch', 'Ankleshwar', 'Navsari', 'Valsad', 'Vapi', 'Mehsana', 'Morbi',
            'Gandhidham', 'Bhuj', 'Porbandar', 'Amreli', 'Surendranagar', 'Palanpur', 'Patan', 'Himmatnagar',
            'Godhra', 'Dahod', 'Botad', 'Veraval', 'Kalol',
        ),
    },
}


def _state_city_q(hub, prefix=''):
    q = Q(**{f'{prefix}state__iexact': hub['name']})
    for name in hub['cities']:
        q |= Q(**{f'{prefix}name__iexact': name})
    return q


def state_hub_agents(agents_qs, hub):
    """Agents serving a city in the state, or whose own pincode is in the state."""
    q = _state_city_q(hub, 'serviceableCities__')
    for prefix in hub['pin_prefixes']:
        q |= Q(agent_pincode__startswith=prefix)
    return agents_qs.filter(q).distinct()


def filter_agents_for_category(agents_qs, category):
    """Narrow an agent queryset to a CITY_CATEGORIES / SERVICE_PAGES entry (services keep everyone)."""
    if category.get('segment'):
        agents_qs = agents_qs.filter(insuranceSegments__segment_type=category['segment']).distinct()
    if category.get('companies'):
        company_q = Q()
        for name in category['companies']:
            company_q |= Q(portfolios__primary_companies__icontains=name)
            company_q |= Q(portfolios__secondary_companies__icontains=name)
        agents_qs = agents_qs.filter(company_q).distinct()
    return agents_qs


def _directory_path(place_slug, key=None):
    if key in SERVICE_PAGES:
        return f"/{key}/{place_slug}/"
    if key:
        return f"/insurance-agents/{place_slug}/{key}/"
    return f"/insurance-agents/{place_slug}/"


def city_agents_directory(request, city_slug, category_slug=None, service_slug=None):
    """
    Programmatic Local SEO Hub: /insurance-agents/<city_slug>/
    Targeting 'insurance agent in <city>', 'best insurance agent in <city>'.

    Multi-tier resolution:
      1. Exact City model match → filter by serviceableCities (M2M)
      2. Known locality/area → filter by servicePincodes / address
      3. Text search on address / agent_pincode fields
      4. City-wide fallback using parent city name
    """
    from apps.agents.models import City
    from django.db.models import Q

    category = None
    if category_slug is not None:
        category = CITY_CATEGORIES.get(str(category_slug).lower())
        if not category:
            from django.http import Http404
            raise Http404("Category not found")
        category_slug = str(category_slug).lower()
    elif service_slug is not None:
        category = SERVICE_PAGES[service_slug]
        category_slug = service_slug

    raw_slug = str(city_slug).strip().lower()
    state_hub = STATE_HUBS.get(raw_slug)
    city_query_name = raw_slug.replace('-', ' ')

    # --- Tier 1: Try exact City model match ---
    city_obj = (
        City.objects.filter(slug=raw_slug).first()
        or City.objects.filter(name__iexact=city_query_name).first()
    )

    area_pincodes = []
    if state_hub:
        city_display = state_hub['name']
        state_display = 'India'
        agents_qs = state_hub_agents(listed_agents_queryset(), state_hub)
    elif city_obj:
        city_display = city_obj.name
        state_display = (city_obj.state or '').strip() or 'India'

        # Use listed_agents_queryset() so PHP-imported agents are included
        base_qs = listed_agents_queryset()
        agents_qs = base_qs.filter(serviceableCities=city_obj).distinct()

        # If very few results, broaden to address/pincode text match as well
        if agents_qs[:5].count() < 5:
            text_q = (
                Q(profile__address__icontains=city_display)
                | Q(profile__office_address__icontains=city_display)
                | Q(serviceableCities__name__icontains=city_display)
            )
            agents_qs = base_qs.filter(text_q).distinct()
    else:
        # --- Tier 2: Check locality/area dictionary ---
        area_pincodes = _resolve_area_to_pincodes(city_query_name)

        # Guess a "parent city" display name from the slug
        # e.g. 'paldi-ahmedabad' → 'Ahmedabad', 'satellite' → 'Satellite'
        parts = city_query_name.split()
        city_display = city_query_name.title()
        state_display = 'India'

        # Detect parent city name in slug parts (common city names)
        _KNOWN_CITIES = {
            'ahmedabad', 'surat', 'rajkot', 'vadodara', 'gandhinagar',
            'mumbai', 'delhi', 'bangalore', 'bengaluru', 'pune', 'hyderabad',
            'chennai', 'kolkata', 'jaipur', 'lucknow', 'indore',
        }
        parent_city_name = None
        for part in parts:
            if part in _KNOWN_CITIES:
                parent_city_name = part.title()
                break

        # For state we can set Gujarat for known Gujarat localities
        _GUJARAT_AREAS = set()
        for _key in _AREA_PINCODE_MAP:
            if any(p.startswith('3') for p in _AREA_PINCODE_MAP[_key]):
                _GUJARAT_AREAS.add(_key)
        if city_query_name in _GUJARAT_AREAS or (parent_city_name and parent_city_name.lower() in {
            'ahmedabad', 'surat', 'rajkot', 'vadodara', 'gandhinagar'
        }):
            state_display = 'Gujarat'

        base_qs = listed_agents_queryset()

        if area_pincodes:
            # Tier 2a: Match agents whose agent_pincode or service_pincodes overlaps
            pin_q = Q()
            for pin in area_pincodes:
                pin_q |= Q(agent_pincode__icontains=pin)
                pin_q |= Q(profile__address__icontains=pin)
                pin_q |= Q(servicePincodes__service_pincode=pin)

            # Also include area name in address
            pin_q |= Q(profile__address__icontains=city_query_name)
            pin_q |= Q(profile__office_address__icontains=city_query_name)

            agents_qs = base_qs.filter(pin_q).distinct()

            # If still sparse, add the parent city agents too
            if agents_qs[:3].count() < 3 and parent_city_name:
                parent_city_obj = City.objects.filter(name__iexact=parent_city_name).first()
                if parent_city_obj:
                    city_qs = base_qs.filter(serviceableCities=parent_city_obj).distinct()
                    agents_qs = (agents_qs | city_qs).distinct()
        else:
            # --- Tier 3: Pure text search on address/city fields ---
            # Cap the OR'd icontains scans an arbitrary slug can trigger.
            tokens = [t.strip() for t in city_query_name.split() if len(t.strip()) >= 3][:3]
            text_q = Q()
            for token in tokens:
                text_q |= Q(profile__address__icontains=token)
                text_q |= Q(profile__office_address__icontains=token)
                text_q |= Q(serviceableCities__name__icontains=token)
                text_q |= Q(agent_pincode__icontains=token)

            agents_qs = base_qs.filter(text_q).distinct()

            # --- Tier 4: Fallback to any agent if nothing found ---
            if not agents_qs.exists() and parent_city_name:
                parent_city_obj = City.objects.filter(name__iexact=parent_city_name).first()
                if parent_city_obj:
                    agents_qs = base_qs.filter(serviceableCities=parent_city_obj).distinct()

    if category:
        agents_qs = filter_agents_for_category(agents_qs, category)

    agents_list = list(
        agents_qs
        .order_by('-created_at')[:200]   # cap to avoid full-table scans
    )
    # Unknown slug with no agents: a real 404, not an indexable "Agents in <anything>" page.
    if not agents_list and not city_obj and not area_pincodes and not state_hub:
        from django.http import Http404
        raise Http404("City not found")

    # Sort by rating descending
    agents_list.sort(key=lambda a: (getattr(a, 'average_rating', 0) or 0), reverse=True)

    # ---- Pagination: 12 cards per page ----
    from django.core.paginator import Paginator, InvalidPage
    paginator = Paginator(agents_list, 12)
    page_num = request.GET.get('page', 1)
    try:
        page_obj = paginator.page(page_num)
    except InvalidPage:
        page_obj = paginator.page(1)

    # Nearby / active cities for internal linking footer
    top_cities = list(
        City.objects.filter(is_active=True, agents__status='active')
        .exclude(slug=raw_slug)
        .exclude(slug__in=JUNK_CITY_SLUGS)
        .exclude(name__iexact=city_display)
        .distinct()[:15]
    )

    state_cities = []
    if state_hub:
        from django.db.models import Count
        state_cities = [
            (_directory_path(c.slug, category_slug), c.name, c.n)
            for c in City.objects.filter(_state_city_q(state_hub), is_active=True,
                                         agents__in=listed_agents_queryset().values('id'))
            .annotate(n=Count('agents', distinct=True)).order_by('-n', 'name')[:40]
            if c.slug
        ]

    canonical_url = request.build_absolute_uri(f"/insurance-agents/{raw_slug}/")
    if page_obj.number > 1:
        # Paginated pages are self-canonical (Google ignores rel=prev/next).
        canonical_url += f"?page={page_obj.number}"
    # Empty pages (no agents) stay reachable but out of the index (soft-404 risk).
    # Tier 3/4 text-search pages (unknown slugs like /insurance-agents/road/) stay out of the index.
    # An area counts only when a whole locality name is in the slug ('road' only partially matches 'sg road').
    known_area = bool(area_pincodes) and any(key in city_query_name for key in _AREA_PINCODE_MAP)
    known_place = bool(state_hub or city_obj or known_area)
    meta_robots = ('index, follow' if known_place and paginator.count >= MIN_INDEXABLE_CITY_AGENTS
                   and raw_slug not in JUNK_CITY_SLUGS else 'noindex, follow')
    meta_title = f"Verified Insurance Agents in {city_display} | Licensed Advisors — PadosiAgent"
    meta_desc = f"Looking for trusted insurance agents in {city_display}? Find verified local advisors for Health, Life, Car & Bike insurance with ratings & doorstep assistance on PadosiAgent."
    meta_kw = f"insurance agent in {city_display}, best insurance agent in {city_display}, insurance agent near me {city_display}, licensed insurance agent {city_display}, health insurance agent {city_display}, life insurance agent {city_display}, PadosiAgent"

    breadcrumb = [
        {'@type': 'ListItem', 'position': 1, 'name': 'Home', 'item': request.build_absolute_uri('/')},
        {'@type': 'ListItem', 'position': 2, 'name': 'Insurance Agents', 'item': request.build_absolute_uri('/find-agents/')},
        {'@type': 'ListItem', 'position': 3, 'name': city_display,
         'item': request.build_absolute_uri(f"/insurance-agents/{raw_slug}/")},
    ]
    if category:
        breadcrumb.append({'@type': 'ListItem', 'position': 4, 'name': f"{category['label']} Agents",
                           'item': request.build_absolute_uri(_directory_path(raw_slug, category_slug))})
    breadcrumb_schema = {'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': breadcrumb}

    from apps.agents.services.og_urls import get_public_site_base
    site_base = get_public_site_base(request)
    list_items = []
    for position, a in enumerate(page_obj.object_list, start=1):
        try:
            photo = a.profile.profile_photo_url if a.profile else ''
        except Exception:
            photo = ''
        item = {
            '@type': 'InsuranceAgency',
            'name': a.fullname or '',
            'url': f"{site_base}/{a.state_code}/{a.agent_slug}/",
        }
        if photo:
            item['image'] = (site_base if photo.startswith('/') else '') + photo
        address = {'@type': 'PostalAddress', 'addressLocality': city_display, 'addressRegion': state_display}
        if a.agent_pincode:
            address['postalCode'] = a.agent_pincode
        address['addressCountry'] = 'IN'
        item['address'] = address
        if a.average_rating and a.review_count:
            item['aggregateRating'] = {'@type': 'AggregateRating',
                                       'ratingValue': str(a.average_rating), 'reviewCount': str(a.review_count)}
        list_items.append({'@type': 'ListItem', 'position': position, 'item': item})
    item_list_schema = {
        '@context': 'https://schema.org',
        '@type': 'ItemList',
        'name': f"Verified {category['label'] if category else 'Insurance'} Agents in {city_display}",
        'description': meta_desc,
        'numberOfItems': paginator.count,
        'itemListElement': list_items,
    }

    category_context = {}
    if category:
        label = category['label']
        canonical_url = canonical_url.replace(f"/insurance-agents/{raw_slug}/", _directory_path(raw_slug, category_slug), 1)
        meta_title = f"{label} Agents in {city_display} - Verified Local Advisors | PadosiAgent"
        count_text = f"{paginator.count}+ " if paginator.count else ''
        meta_desc = (f"Looking for a trusted {label if label.isupper() else label.lower()} agent in {city_display}? Compare {count_text}verified local "
                     f"advisors with ratings and reviews. Connect directly on call or WhatsApp for free claim guidance.")
        meta_kw = category['keywords'].format(city=city_display) + ', PadosiAgent'
        faqs = [(q.format(city=city_display), a.format(city=city_display)) for q, a in category['faqs']]
        category_context = {
            'category': category,
            'category_slug': category_slug,
            'category_intro': category['intro'].format(city=city_display),
            'faqs': faqs,
            'faq_schema': {
                '@context': 'https://schema.org',
                '@type': 'FAQPage',
                'mainEntity': [
                    {'@type': 'Question', 'name': q, 'acceptedAnswer': {'@type': 'Answer', 'text': a}}
                    for q, a in faqs
                ],
            },
        }

    context = {
        **category_context,
        'breadcrumb_schema': breadcrumb_schema,
        'item_list_schema': item_list_schema,
        'city_categories': [(_directory_path(raw_slug, slug), c['label'])
                            for slug, c in {**CITY_CATEGORIES, **SERVICE_PAGES}.items() if slug != category_slug],
        'state_cities': state_cities,
        'city_name': city_display,
        'state_name': state_display,
        'city_slug': raw_slug,
        'agents': page_obj.object_list,
        'agent_count': paginator.count,
        'page_obj': page_obj,
        'paginator': paginator,
        'top_cities': top_cities,
        'canonical_url': canonical_url,
        'meta_title': meta_title,
        'meta_description': meta_desc,
        'meta_keywords': meta_kw,
        'meta_robots': meta_robots,
    }
    return render(request, 'public/city_directory.html', context)
