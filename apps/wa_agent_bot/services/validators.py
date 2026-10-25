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
    Returns (True, cleaned_name) or (False, error_message).
    """
    name = text.strip()
    if not name:
        return False, "Name cannot be empty. Please enter your full name."
    if len(name) < 3:
        return False, "Name is too short. Please enter at least 3 characters."
    if len(name) > 70:
        return False, "Name is too long. Please keep it under 70 characters."
    # Only allow letters, spaces, dots, and hyphens
    if not re.match(r'^[a-zA-Z\s.\-\']+$', name):
        return False, "Name should only contain letters, spaces, dots, and hyphens."
    return True, name


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


def validate_state_selection(text, states_list=None):
    """
    Validate state selection (by number or name).
    Returns (True, state_name) or (False, error_message).
    """
    if states_list is None:
        states_list = INDIAN_STATES

    cleaned = text.strip()

    # Check if input is a number (selection from numbered list)
    if cleaned.isdigit():
        idx = int(cleaned) - 1  # 1-indexed
        if 0 <= idx < len(states_list):
            return True, states_list[idx]
        return False, f"Invalid selection. Please enter a number between 1 and {len(states_list)}."

    # Check if input matches a state name (case-insensitive)
    cleaned_lower = cleaned.lower()
    for state in states_list:
        if state.lower() == cleaned_lower:
            return True, state
    # Fuzzy partial match
    for state in states_list:
        if cleaned_lower in state.lower():
            return True, state

    return False, "State not found. Please enter the number from the list or the full state name."


def validate_pincode(text):
    """
    Validate Indian pincode (6 digits).
    Returns (True, cleaned_pincode) or (False, error_message).
    """
    pincode = re.sub(r'\D', '', text.strip())
    if len(pincode) != 6:
        return False, "Please enter a valid 6-digit pincode."
    if pincode[0] == '0':
        return False, "That doesn't look like a valid Indian pincode. The first digit can't be 0."
    return True, pincode


def validate_experience_selection(text):
    """
    Validate experience range selection.
    Returns (True, experience_string) or (False, error_message).
    """
    cleaned = text.strip()

    # Check if input is a number
    if cleaned.isdigit():
        idx = int(cleaned) - 1
        if 0 <= idx < len(EXPERIENCE_RANGES):
            return True, EXPERIENCE_RANGES[idx]
        return False, f"Invalid selection. Please enter a number between 1 and {len(EXPERIENCE_RANGES)}."

    # Match by text
    cleaned_lower = cleaned.lower()
    for exp in EXPERIENCE_RANGES:
        if cleaned_lower in exp.lower() or exp.lower() in cleaned_lower:
            return True, exp

    return False, "Invalid selection. Please choose from the numbered list."


def validate_segments_selection(text):
    """
    Validate insurance segments selection (comma-separated numbers or names).
    Returns (True, list_of_segment_ids) or (False, error_message).
    """
    cleaned = text.strip()
    if not cleaned:
        return False, "Please select at least one segment."

    selected_ids = []

    # Split by comma, space, or both
    parts = re.split(r'[,\s]+', cleaned)

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
        else:
            # Match by name
            matched = False
            for seg in INSURANCE_SEGMENTS:
                if part.lower() in seg['label'].lower() or seg['label'].lower() in part.lower():
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
