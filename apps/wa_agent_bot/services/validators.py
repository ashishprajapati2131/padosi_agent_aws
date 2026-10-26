"""
WhatsApp Agent Bot — Input Validators

All validation functions for registration data collected during the
WhatsApp conversation flow. Returns (is_valid, cleaned_value_or_error).
"""

import re


# ── Indian states for registration ──────────────────────────────────────
INDIAN_STATES = [
    'Andhra Pradesh', 'Arunachal Pradesh', 'Assam', 'Bihar', 'Chhattisgarh',
    'Goa', 'Gujarat', 'Haryana', 'Himachal Pradesh', 'Jharkhand',
    'Karnataka', 'Kerala', 'Madhya Pradesh', 'Maharashtra', 'Manipur',
    'Meghalaya', 'Mizoram', 'Nagaland', 'Odisha', 'Punjab',
    'Rajasthan', 'Sikkim', 'Tamil Nadu', 'Telangana', 'Tripura',
    'Uttar Pradesh', 'Uttarakhand', 'West Bengal',
    'Andaman and Nicobar Islands', 'Chandigarh',
    'Dadra and Nagar Haveli and Daman and Diu',
    'Delhi', 'Jammu and Kashmir', 'Ladakh', 'Lakshadweep', 'Puducherry',
]

# ── Experience ranges ───────────────────────────────────────────────────
EXPERIENCE_RANGES = [
    '0-2 years',
    '2-5 years',
    '5-10 years',
    '10+ years',
]

# ── Insurance segments ──────────────────────────────────────────────────
INSURANCE_SEGMENTS = [
    {'id': 'health', 'label': 'Health'},
    {'id': 'life', 'label': 'Life'},
    {'id': 'motor', 'label': 'Motor'},
    {'id': 'sme', 'label': 'SME'},
]


def validate_fullname(text):
    """
    Validate the agent's full name.
    Supports English, Gujarati, Hindi, and Indian names with salutations.
    Returns (True, cleaned_name) or (False, error_message).
    """
    name = text.strip()
    if not name:
        return False, "Name cannot be empty. Please enter your full name."
    if len(name) < 2:
        return False, "Name is too short. Please enter at least 2 characters."
    if len(name) > 70:
        return False, "Name is too long. Please keep it under 70 characters."
    # Disallow numbers or special symbols except letters, spaces, dots, hyphens, apostrophes
    if re.search(r'[\d!@#$%^&*()_+={}\[\]:;"<>?\/\\|`~]', name):
        return False, "Name should only contain letters, spaces, dots, and hyphens."
    cleaned = re.sub(r'\s+', ' ', name)
    return True, cleaned.title() if cleaned.isascii() else cleaned


def validate_email(text):
    """
    Validate email address format.
    Returns (True, cleaned_email) or (False, error_message).
    """
    email = text.strip().lower()
    if not email:
        return False, "Email cannot be empty. Please enter your email address."
    # Simple but effective email regex
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False, "That doesn't look like a valid email. Please enter a valid email address (e.g., name@example.com)."
    return True, email


def validate_mobile(text):
    """
    Validate Indian mobile number (10 digits).
    Returns (True, cleaned_mobile) or (False, error_message).
    """
    # Remove all non-digit characters
    mobile = re.sub(r'\D', '', text.strip())
    # Remove country code if present
    if mobile.startswith('91') and len(mobile) == 12:
        mobile = mobile[2:]
    if mobile.startswith('0') and len(mobile) == 11:
        mobile = mobile[1:]
    if len(mobile) != 10:
        return False, "Please enter a valid 10-digit mobile number."
    if not mobile[0] in '6789':
        return False, "Please enter a valid Indian mobile number (should start with 6, 7, 8, or 9)."
    return True, mobile


def extract_clean_phone(phone_str):
    """
    Extract a valid 10-digit Indian phone number from any string,
    cleaning out country code (+91, 91), leading zero, and punctuation.
    Returns 10-digit string or None.
    """
    if not phone_str:
        return None
    digits = re.sub(r'\D', '', str(phone_str))
    if digits.startswith('91') and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith('0') and len(digits) == 11:
        digits = digits[1:]
    if len(digits) == 10 and digits[0] in '6789':
        return digits
    return None


def parse_contact_input(text):
    """
    Intelligently parse user input that may contain an email, a mobile number,
    or BOTH concatenated or separated by spaces/symbols.
    
    Examples supported:
      - '6352701899parthsadhu0309@gmail.com' -> mobile + email
      - 'parthsadhu0309@gmail.com6352701899' -> email + mobile
      - '6352701899 parthsadhu0309@gmail.com' -> mobile + email
      - '+91 6352701899 / rajesh@gmail.com'   -> mobile + email
      - 'parthsadhu0309@gmail.com'            -> email only
      - '6352701899'                          -> mobile only
    
    Returns:
      dict: {'email': email_str or None, 'mobile': mobile_str or None}
    """
    if not text:
        return {'email': None, 'mobile': None}

    cleaned = text.strip()

    # 1. Check direct concatenated mobile+email or email+mobile
    # E.g. '6352701899parthsadhu0309@gmail.com'
    concat_m_e = re.match(
        r'^(?:\+?91|0)?([6-9]\d{9})\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})$',
        cleaned,
        re.IGNORECASE
    )
    if concat_m_e:
        return {'mobile': concat_m_e.group(1), 'email': concat_m_e.group(2).lower()}

    # E.g. 'parthsadhu0309@gmail.com6352701899'
    concat_e_m = re.match(
        r'^([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\s*(?:\+?91|0)?([6-9]\d{9})$',
        cleaned,
        re.IGNORECASE
    )
    if concat_e_m:
        return {'email': concat_e_m.group(1).lower(), 'mobile': concat_e_m.group(2)}

    # 2. General search for email in the text
    email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', cleaned)
    found_email = email_match.group(0).lower() if email_match else None

    # 3. For mobile, remove the matched email from text first to avoid digit collisions
    remaining = cleaned
    if email_match:
        remaining = cleaned[:email_match.start()] + ' ' + cleaned[email_match.end():]

    # Check if remaining text has a 10-digit mobile number
    mob_match = re.search(r'(?:(?<=\D)|^)(?:\+?91|0)?([6-9]\d{9})(?:(?=\D)|$)', remaining)
    found_mobile = mob_match.group(1) if mob_match else None

    # Fallback: check if entire remaining string cleans down to a valid mobile
    if not found_mobile:
        found_mobile = extract_clean_phone(remaining)

    return {'email': found_email, 'mobile': found_mobile}


# ── State aliases & common abbreviations / major cities ──────────────────
STATE_ALIASES = {
    'gj': 'Gujarat', 'gujrat': 'Gujarat', 'gujarat': 'Gujarat', 'guj': 'Gujarat',
    'ahmedabad': 'Gujarat', 'surat': 'Gujarat', 'vadodara': 'Gujarat', 'rajkot': 'Gujarat', 'gandhinagar': 'Gujarat',
    'mh': 'Maharashtra', 'maharastra': 'Maharashtra', 'maharashtra': 'Maharashtra', 'maha': 'Maharashtra',
    'mumbai': 'Maharashtra', 'pune': 'Maharashtra', 'nagpur': 'Maharashtra', 'nashik': 'Maharashtra', 'thane': 'Maharashtra',
    'dl': 'Delhi', 'delhi': 'Delhi', 'new delhi': 'Delhi', 'ncr': 'Delhi', 'delhi ncr': 'Delhi',
    'rj': 'Rajasthan', 'rajasthan': 'Rajasthan', 'jaipur': 'Rajasthan', 'rajastan': 'Rajasthan', 'jodhpur': 'Rajasthan', 'udaipur': 'Rajasthan',
    'mp': 'Madhya Pradesh', 'madhya pradesh': 'Madhya Pradesh', 'indore': 'Madhya Pradesh', 'bhopal': 'Madhya Pradesh',
    'up': 'Uttar Pradesh', 'uttar pradesh': 'Uttar Pradesh', 'lucknow': 'Uttar Pradesh', 'kanpur': 'Uttar Pradesh', 'noida': 'Uttar Pradesh', 'varanasi': 'Uttar Pradesh',
    'ka': 'Karnataka', 'karnataka': 'Karnataka', 'karnatak': 'Karnataka', 'bangalore': 'Karnataka', 'bengaluru': 'Karnataka',
    'tn': 'Tamil Nadu', 'tamil nadu': 'Tamil Nadu', 'tamilnadu': 'Tamil Nadu', 'chennai': 'Tamil Nadu',
    'wb': 'West Bengal', 'west bengal': 'West Bengal', 'kolkata': 'West Bengal', 'bengal': 'West Bengal',
    'tg': 'Telangana', 'ts': 'Telangana', 'telangana': 'Telangana', 'hyderabad': 'Telangana',
    'ap': 'Andhra Pradesh', 'andhra pradesh': 'Andhra Pradesh', 'andhra': 'Andhra Pradesh', 'vizag': 'Andhra Pradesh',
    'kl': 'Kerala', 'kerala': 'Kerala', 'kochi': 'Kerala', 'trivandrum': 'Kerala',
    'hr': 'Haryana', 'haryana': 'Haryana', 'gurgaon': 'Haryana', 'gurugram': 'Haryana', 'faridabad': 'Haryana',
    'pb': 'Punjab', 'punjab': 'Punjab', 'amritsar': 'Punjab', 'ludhiana': 'Punjab',
    'br': 'Bihar', 'bihar': 'Bihar', 'patna': 'Bihar',
    'or': 'Odisha', 'odisha': 'Odisha', 'orissa': 'Odisha', 'bhubaneswar': 'Odisha',
    'jh': 'Jharkhand', 'jharkhand': 'Jharkhand', 'ranchi': 'Jharkhand',
    'as': 'Assam', 'assam': 'Assam', 'guwahati': 'Assam',
    'ch': 'Chandigarh', 'chandigarh': 'Chandigarh',
    'ga': 'Goa', 'goa': 'Goa',
    'uk': 'Uttarakhand', 'uttarakhand': 'Uttarakhand', 'uttaranchal': 'Uttarakhand', 'dehradun': 'Uttarakhand',
    'hp': 'Himachal Pradesh', 'himachal': 'Himachal Pradesh', 'shimla': 'Himachal Pradesh',
}


def validate_state_selection(text, states_list=None):
    """
    Validate state selection (by number, abbreviation, city or state name).
    Returns (True, state_name) or (False, error_message).
    """
    if states_list is None:
        states_list = INDIAN_STATES

    cleaned = text.strip()
    cleaned_lower = cleaned.lower()

    # 1. Selection by number (1-indexed)
    if cleaned.isdigit():
        idx = int(cleaned) - 1
        if 0 <= idx < len(states_list):
            return True, states_list[idx]
        return False, f"Invalid selection. Please enter a number between 1 and {len(states_list)}."

    # 2. Check alias / abbreviation / major city dictionary
    if cleaned_lower in STATE_ALIASES:
        state_name = STATE_ALIASES[cleaned_lower]
        if state_name in states_list:
            return True, state_name

    # 3. Exact case-insensitive match
    for state in states_list:
        if state.lower() == cleaned_lower:
            return True, state

    # 4. Partial substring match
    for state in states_list:
        if cleaned_lower in state.lower():
            return True, state

    return False, "State not found. Please enter the number from the list or the full state name (e.g., Gujarat)."


def validate_pincode(text):
    """
    Validate Indian pincode (6 digits).
    Extracts 6-digit pincode even if user types surrounding text.
    Returns (True, cleaned_pincode) or (False, error_message).
    """
    cleaned = text.strip()
    if not cleaned:
        return False, "Pincode cannot be empty. Please enter your 6-digit area pincode."

    # 1. Search for 6-digit number bounded by words
    match = re.search(r'\b([1-9]\d{5})\b', cleaned)
    if match:
        return True, match.group(1)

    # 2. Clean all non-digits
    digits = re.sub(r'\D', '', cleaned)
    if len(digits) == 6:
        if digits[0] == '0':
            return False, "That doesn't look like a valid Indian pincode. The first digit can't be 0."
        return True, digits

    return False, "Please enter a valid 6-digit area pincode (e.g., 380015)."


def validate_experience_selection(text):
    """
    Validate experience range selection.
    Supports option numbers (1-4), range text (e.g. '2-5 years'),
    keywords ('fresher'), or direct years (e.g. '3 years', '5 yrs').
    Returns (True, experience_string) or (False, error_message).
    """
    cleaned = text.strip().lower()

    # 1. Direct option number 1 to 4
    if cleaned in ('1', '1.', 'one'):
        return True, EXPERIENCE_RANGES[0]
    elif cleaned in ('2', '2.', 'two'):
        return True, EXPERIENCE_RANGES[1]
    elif cleaned in ('3', '3.', 'three'):
        return True, EXPERIENCE_RANGES[2]
    elif cleaned in ('4', '4.', 'four'):
        return True, EXPERIENCE_RANGES[3]

    # 2. Direct range match
    if '0-2' in cleaned or '0 to 2' in cleaned:
        return True, EXPERIENCE_RANGES[0]
    if '2-5' in cleaned or '2 to 5' in cleaned:
        return True, EXPERIENCE_RANGES[1]
    if '5-10' in cleaned or '5 to 10' in cleaned:
        return True, EXPERIENCE_RANGES[2]
    if '10+' in cleaned or '10 +' in cleaned or 'more than 10' in cleaned or 'above 10' in cleaned:
        return True, EXPERIENCE_RANGES[3]

    # 3. Fresher / beginner
    if any(w in cleaned for w in ('fresh', 'new', 'start', 'beginner', 'learn')):
        return True, EXPERIENCE_RANGES[0]

    # 4. If year mentioned, like '3 years', '7 yrs', '15 years'
    yr_match = re.search(r'(\d{1,2})\s*(?:years?|yrs?)', cleaned)
    if yr_match:
        yrs = int(yr_match.group(1))
        if yrs <= 2:
            return True, EXPERIENCE_RANGES[0]
        elif yrs <= 5:
            return True, EXPERIENCE_RANGES[1]
        elif yrs <= 10:
            return True, EXPERIENCE_RANGES[2]
        else:
            return True, EXPERIENCE_RANGES[3]

    # 5. Fallback text search in predefined ranges
    for exp in EXPERIENCE_RANGES:
        if cleaned in exp.lower() or exp.lower() in cleaned:
            return True, exp

    return False, "Invalid selection. Please choose from 1 to 4 or type your years of experience."


def validate_segments_selection(text):
    """
    Validate insurance segments selection.
    Supports:
    - Comma/space separated numbers (e.g. '1, 2' or '1 2')
    - Compact numbers (e.g. '12' or '123')
    - Segment names (e.g. 'Health and Life', 'Motor')
    - 'all' / 'every' / 'badha' -> all 4 segments
    - 'general' / 'GI' -> motor, health, sme
    Returns (True, list_of_segment_ids) or (False, error_message).
    """
    cleaned = text.strip().lower()
    if not cleaned:
        return False, "Please select at least one segment."

    all_ids = [s['id'] for s in INSURANCE_SEGMENTS]

    # Quick check for 'all' or 'badha'
    if any(w in cleaned for w in ('all', 'badha', 'every', 'char', 'chaar', 'both')):
        return True, all_ids

    # Remove noise words like 'and', '&', '+', 'aur', 'ane', 'with'
    cleaned_norm = re.sub(r'\b(and|aur|ane|plus|with)\b|[&+/]', ' ', cleaned)

    # Check if user typed compact digits like '12', '123', '1234', '134'
    compact_match = re.match(r'^[1-4]{2,4}$', cleaned_norm.strip())
    if compact_match:
        digits = list(cleaned_norm.strip())
        selected = [INSURANCE_SEGMENTS[int(d)-1]['id'] for d in digits]
        return True, list(dict.fromkeys(selected))

    selected_ids = []
    parts = re.split(r'[,\s]+', cleaned_norm)

    for part in parts:
        part = part.strip()
        if not part:
            continue

        if part.isdigit():
            idx = int(part) - 1
            if 0 <= idx < len(INSURANCE_SEGMENTS):
                seg_id = INSURANCE_SEGMENTS[idx]['id']
                if seg_id not in selected_ids:
                    selected_ids.append(seg_id)
            else:
                return False, f"Invalid number: {part}. Please enter numbers between 1 and {len(INSURANCE_SEGMENTS)}."
        elif part in ('general', 'gi'):
            for sid in ('motor', 'health', 'sme'):
                if sid not in selected_ids:
                    selected_ids.append(sid)
        else:
            matched = False
            for seg in INSURANCE_SEGMENTS:
                if part in seg['label'].lower() or seg['label'].lower() in part:
                    if seg['id'] not in selected_ids:
                        selected_ids.append(seg['id'])
                    matched = True
                    break
            if not matched:
                return False, f"Unknown segment: '{part}'. Please choose from the numbered list."

    if not selected_ids:
        return False, "Please select at least one segment."

    return True, selected_ids


def format_segments_display(segment_ids):
    """Convert segment IDs to display labels."""
    label_map = {seg['id']: seg['label'] for seg in INSURANCE_SEGMENTS}
    return ', '.join(label_map.get(sid, sid) for sid in segment_ids)


def format_states_list():
    """Format the states list as a numbered WhatsApp message."""
    lines = []
    for i, state in enumerate(INDIAN_STATES, 1):
        lines.append(f"{i}. {state}")
    return '\n'.join(lines)


def format_experience_list():
    """Format experience ranges as a numbered WhatsApp message."""
    lines = []
    for i, exp in enumerate(EXPERIENCE_RANGES, 1):
        lines.append(f"{i}. {exp}")
    return '\n'.join(lines)


def format_segments_list():
    """Format insurance segments as a numbered WhatsApp message."""
    lines = []
    for i, seg in enumerate(INSURANCE_SEGMENTS, 1):
        lines.append(f"{i}. {seg['label']}")
    return '\n'.join(lines)
