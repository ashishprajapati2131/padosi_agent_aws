"""Write flows for the admin Find Agent Locator (views/find_agent_locator.py).

Geocoding HTTP calls stay in the view module.
"""

import json
import logging
from decimal import Decimal

from django.utils import timezone

from apps.agents.models import PaymentStatus
from apps.agents.models import Agent, AgentProfile, AgentSubscription
from apps.admin_panel.models import AgentServicePincode
from apps.home.models import Pincode, PincodeCache

# Same logger name as before the move, so log routing/filters are unchanged.
logger = logging.getLogger("apps.admin_panel.views.find_agent_locator")


def save_pincode_to_master(pincode, lat, lng, office_name, district, state, division, taluk):
    """Store coordinates in PincodeCache and upsert the Pincode row. Returns created."""
    # Save to PincodeCache
    display_name = f"{office_name}, {district}, {state}"
    PincodeCache.store_coordinates(pincode, lat, lng, display_name)

    # Update or create in Pincode model
    existing = Pincode.objects.filter(pincode=pincode).first()
    if existing:
        Pincode.objects.filter(pincode=pincode).update(
            office_name=office_name,
            district=district,
            state=state,
            latitude=Decimal(str(round(lat, 8))),
            longitude=Decimal(str(round(lng, 8))),
            division=division,
            taluk=taluk,
            updated_at=timezone.now(),
        )
        created = False
    else:
        Pincode.objects.create(
            pincode=pincode,
            office_name=office_name,
            district=district,
            state=state,
            latitude=Decimal(str(round(lat, 8))),
            longitude=Decimal(str(round(lng, 8))),
            division=division,
            taluk=taluk,
        )
        created = True

    return created


def assign_agent_to_pincode(agent, pincode, city_name, lat, lng,
                            set_primary, add_service_pin, activate_agent):
    update_fields = ['updated_at']

    # 1. Update Primary coordinates & pincode if requested
    if set_primary:
        agent.agent_pincode = pincode
        agent.latitude = Decimal(str(round(lat, 8)))
        agent.longitude = Decimal(str(round(lng, 8)))
        update_fields.extend(['agent_pincode', 'latitude', 'longitude'])

    # 2. Activate agent and profile visibility
    if activate_agent:
        if agent.status != 'active':
            agent.status = 'active'
            agent.is_approved = True
            if not agent.approved_at:
                agent.approved_at = timezone.now()
            update_fields.extend(['status', 'is_approved', 'approved_at'])

    agent.save(update_fields=list(set(update_fields)))

    # Ensure profile exists and is visible
    profile, _ = AgentProfile.objects.get_or_create(
        agent=agent,
        defaults={'display_name': agent.fullname, 'is_card_visible': True, 'is_profile_visible': True}
    )

    if activate_agent:
        profile.is_card_visible = True
        profile.is_profile_visible = True

    # 3. Add to Service Pincodes list
    if add_service_pin:
        # Add to profile.service_pincodes JSON array
        current_pins = profile.service_pincodes or []
        if isinstance(current_pins, str):
            try:
                current_pins = json.loads(current_pins)
            except Exception:
                current_pins = [current_pins]
        if not isinstance(current_pins, list):
            current_pins = []

        # Check if pincode already exists
        exists_in_json = any(
            (p == pincode) or (isinstance(p, dict) and p.get('pincode') == pincode)
            for p in current_pins
        )
        if not exists_in_json:
            current_pins.append({
                'pincode': pincode,
                'city_name': city_name,
                'added_at': timezone.now().isoformat()
            })
            profile.service_pincodes = current_pins

        profile.save()

        # Add to AgentServicePincode table
        try:
            AgentServicePincode.objects.update_or_create(
                agent=agent,
                service_pincode=pincode,
                defaults={
                    'city_name': city_name,
                    'selected_areas_json': [city_name],
                    'postal_data_json': {
                        'pincode': pincode,
                        'lat': lat,
                        'lng': lng,
                        'city': city_name
                    },
                    'updated_at': timezone.now(),
                }
            )
        except Exception as e:
            logger.warning(f"[FindAgentLocator] AgentServicePincode insert warning: {e}")


def create_agent(fullname, email, mobile, pincode, insurance_type, company_name, city_name, lat, lng):
    """Create the agent, profile, free-trial subscription and service pincode. Returns agent."""
    from apps.agents.services.account_auth import create_or_link_django_user

    now = timezone.now()
    agent = Agent.objects.create(
        fullname=fullname,
        email=email,
        mobile=mobile,
        agent_pincode=pincode,
        latitude=Decimal(str(round(lat, 8))),
        longitude=Decimal(str(round(lng, 8))),
        status='active',
        is_approved=True,
        approved_at=now,
        registration_step=4,
        plan_type='free_trial',
        trial_ends_at=now + timezone.timedelta(days=365),
        insurance_companies=[company_name] if company_name else ['LIC'],
        user_types=[insurance_type.lower()] if insurance_type else ['life'],
    )

    try:
        create_or_link_django_user(agent)
    except Exception as _user_err:
        logger.warning(f"Could not link Django user for quick-created agent {agent.id}: {_user_err}")

    AgentProfile.objects.create(
        agent=agent,
        display_name=fullname,
        service_pincodes=[{
            'pincode': pincode,
            'city_name': city_name,
            'added_at': now.isoformat()
        }],
        address=city_name,
        state=city_name,
        is_card_visible=True,
        is_profile_visible=True,
        experience_years=3,
    )

    AgentSubscription.objects.create(
        agent=agent,
        selected_plan='free_trial',
        registration_amount=Decimal('0.00'),
        payment_status=PaymentStatus.COMPLETED,
        status='active',
        starts_at=now,
        expires_at=now + timezone.timedelta(days=365),
    )

    try:
        AgentServicePincode.objects.create(
            agent=agent,
            service_pincode=pincode,
            city_name=city_name,
            selected_areas_json=[city_name],
            postal_data_json={
                'pincode': pincode,
                'lat': lat,
                'lng': lng,
                'city': city_name
            },
        )
    except Exception:
        pass

    return agent


def unlink_agent_pincode(agent, pincode):
    # Delete from AgentServicePincode table
    AgentServicePincode.objects.filter(agent=agent, service_pincode=pincode).delete()

    # Remove from profile.service_pincodes
    profile = getattr(agent, 'profile', None)
    if profile and profile.service_pincodes:
        pins = profile.service_pincodes
        if isinstance(pins, list):
            new_pins = []
            for p in pins:
                if isinstance(p, dict) and p.get('pincode') == pincode:
                    continue
                if isinstance(p, str) and p == pincode:
                    continue
                new_pins.append(p)
            profile.service_pincodes = new_pins
            profile.save(update_fields=['service_pincodes', 'updated_at'])

    # If primary pincode was this pincode, clear it
    if agent.agent_pincode == pincode:
        agent.agent_pincode = ''
        agent.save(update_fields=['agent_pincode', 'updated_at'])
