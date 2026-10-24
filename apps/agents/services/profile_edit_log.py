"""Field list and diff for agent profile edit history (admin approvals drawer).

Shared by the website save (apps/agents/views/dashboard.py) and the mobile API
save (fastapi_app/services/profile_service.py) so both log identical rows.
Snapshot keys: Agent columns by name, AgentProfile columns as 'profile.<name>',
child tables by the CHILD_FORMATS key.
"""
import json
import os

BASIC, PROFESSIONAL, PORTFOLIO, ADDITIONAL = (
    'Basic Info', 'Professional Details', 'Portfolio & Segments', 'Additional Info')

# key -> (edit-profile section, label). Only these are diffed, so internal
# columns (payment, referral, approval flags, tokens...) never show up as edits.
FIELDS = {
    'fullname': (BASIC, 'Full Name'),
    'email': (BASIC, 'Email'),
    'mobile': (BASIC, 'Mobile'),
    'user_types': (BASIC, 'User Types'),
    'profile.display_name': (BASIC, 'Display Name'),
    'profile.whatsapp': (BASIC, 'WhatsApp'),
    'profile.languages': (BASIC, 'Languages'),
    'profile.address': (BASIC, 'Address'),
    'profile.state': (BASIC, 'State'),
    'profile.date_of_birth': (BASIC, 'Date of Birth'),
    'profile.profile_photo_path': (BASIC, 'Profile Photo'),

    'profession': (PROFESSIONAL, 'Profession'),
    'experience_range': (PROFESSIONAL, 'Years of Experience'),
    'profile.experience_years': (PROFESSIONAL, 'Experience (Years)'),
    'client_base': (PROFESSIONAL, 'Client Base'),
    'insurance_companies': (PROFESSIONAL, 'Insurance Companies'),
    'agent_pincode': (PROFESSIONAL, 'Pincode'),
    'profile.pan_number': (PROFESSIONAL, 'PAN Number'),
    'profile.license_number': (PROFESSIONAL, 'IRDAI License No.'),
    'profile.license_valid_till': (PROFESSIONAL, 'IRDAI License Valid Till'),
    'profile.irdai_license_doc': (PROFESSIONAL, 'IRDAI License Document'),
    'profile.arn_number': (PROFESSIONAL, 'ARN Number'),
    'profile.euin_number': (PROFESSIONAL, 'EUIN Number'),
    'profile.investment_valid_till': (PROFESSIONAL, 'Investment License Valid Till'),
    'profile.amfi_license_doc': (PROFESSIONAL, 'AMFI License Document'),
    'profile.agency_name': (PROFESSIONAL, 'Agency Name'),
    'profile.office_address': (PROFESSIONAL, 'Office Address'),
    'profile.has_pos_license': (PROFESSIONAL, 'POS License'),
    'profile.service_pincodes': (PROFESSIONAL, 'Service Pincodes'),
    'service_areas': (PROFESSIONAL, 'Service Areas'),
    'serviceable_cities': (PROFESSIONAL, 'Serviceable Cities'),
    'family_licenses': (PROFESSIONAL, 'Family Licenses'),
    'performance_stats': (PROFESSIONAL, 'Claims Performance'),
    'lead_preferences': (PROFESSIONAL, 'Lead Preferences'),

    'insurance_segments': (PORTFOLIO, 'Insurance Segments'),
    'profile.investment_types': (PORTFOLIO, 'Investment Types'),
    'product_expertise': (PORTFOLIO, 'Product Expertise'),
    'portfolios': (PORTFOLIO, 'Company Portfolio'),
    'profile.portfolio_breakdown': (PORTFOLIO, 'Portfolio Breakdown'),
    'profile.software_name': (PORTFOLIO, 'Software Used'),
    'profile.desired_services': (PORTFOLIO, 'Desired Services'),

    'profile.website_url': (ADDITIONAL, 'Website'),
    'profile.social_links': (ADDITIONAL, 'Social Links'),
    'profile.career_highlights': (ADDITIONAL, 'Professional Bio'),
    'achievement_photos': (ADDITIONAL, 'Achievement Photos'),
    'career_timeline': (ADDITIONAL, 'Career Timeline'),

    'badge': ('Admin', 'Badge'),
}


def _yes(v):
    return 'Yes' if v else 'No'


def _json(v):
    if isinstance(v, (str, bytes)):
        try:
            return json.loads(v)
        except (ValueError, TypeError):
            return v
    return v


def _companies(v):
    """'LIC 60%, HDFC 40%' from the web dict shape or the app's JSON list shape."""
    out = []

    def walk(x):
        x = _json(x)
        if isinstance(x, list):
            for i in x:
                walk(i)
        elif isinstance(x, dict):
            if x.get('companies'):
                walk(x['companies'])
            elif x.get('name'):
                pct = x.get('percent') or x.get('percentage') or ''
                out.append(f"{x['name']} {pct}%".strip() if pct else str(x['name']))
            if x.get('others'):
                out.append(f"Others: {x['others']}")
        elif x:
            out.append(str(x))

    walk(v)
    return ', '.join(dict.fromkeys(out))


def _areas(v):
    v = _json(v)
    return ', '.join(map(str, v)) if isinstance(v, list) else (str(v) if v else '')


# child key -> (row formatter, row separator). Each row is the tuple of columns
# both callers query, in the order noted.
CHILD_FORMATS = {
    # (segment_type,)
    'insurance_segments': (lambda r: r[0], ', '),
    # (city name,)
    'serviceable_cities': (lambda r: r[0], ', '),
    # (service_pincode, city_name, selected_areas_json)
    'service_areas': (lambda r: f'{r[0]} {r[1]}: {_areas(r[2])}'.strip(' :'), ' | '),
    # (segment_type, product_name, expertise_level)
    'product_expertise': (lambda r: f'{r[0]} / {r[1]}: level {r[2]}', ' | '),
    # (full_name, relationship, license_number)
    'family_licenses': (lambda r: f'{r[0]} ({r[1]}) {r[2] or ""}'.strip(), ' | '),
    # (segment_type, primary_companies, secondary_companies)
    'portfolios': (lambda r: f'{r[0]}: {_companies([r[1], r[2]])}', ' | '),
    # (claims_processed, claims_settled, claims_amount, response_time)
    'performance_stats': (lambda r: f'Processed {r[0]}, Settled {r[1]}, Amount ₹{r[2]}, Response {r[3]} hrs', ' | '),
    # (leads_new_business, leads_portfolio_analysis, portfolio_charging, portfolio_fee,
    #  leads_claims_support, claims_charging, claims_fee_amount, claims_percent)
    'lead_preferences': (lambda r: (
        f'New business: {_yes(r[0])}; Portfolio analysis: {_yes(r[1])} ({r[2] or "-"}, fee {r[3] or 0}); '
        f'Claims support: {_yes(r[4])} ({r[5] or "-"}, fee {r[6] or 0}, {r[7] or 0}%)'), ' | '),
    # (photo_path,)
    'achievement_photos': (lambda r: os.path.basename(str(r[0])), ', '),
    # (month, year, event_type, event_text)
    'career_timeline': (lambda r: f'{r[0]} {r[1]} {r[2]}: {r[3]}'.strip(), ' | '),
}


def snapshot_value(value):
    if value is None:
        return ''
    if isinstance(value, bool):
        return _yes(value)
    if isinstance(value, (dict, list)):
        if value and all(isinstance(v, str) for v in (value.values() if isinstance(value, dict) else value)):
            if isinstance(value, dict):
                return ', '.join(f'{k}: {v}' for k, v in sorted(value.items()) if v)
            return ', '.join(value)
        return json.dumps(value, sort_keys=True, default=str)
    return str(value)


def child_snapshot(rows_by_key):
    """{key: iterable of row tuples} -> {key: sorted readable text}."""
    snap = {}
    for key, rows in rows_by_key.items():
        fmt, sep = CHILD_FORMATS[key]
        snap[key] = sep.join(sorted(str(fmt(tuple(r))) for r in rows))
    return snap


def build_changes(before, after):
    """Changed FIELDS between two snapshots, in edit-profile section order."""
    changes = []
    for key, (section, label) in FIELDS.items():
        if key not in after:
            continue
        old, new = before.get(key, ''), after[key]
        if old != new:
            changes.append({'field': key, 'section': section, 'label': label,
                            'old_value': old, 'new_value': new})
    return changes
