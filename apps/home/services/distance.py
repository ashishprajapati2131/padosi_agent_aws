import math
import re
import json
import logging
from apps.home.models import Pincode

logger = logging.getLogger(__name__)

_PIN_RE = re.compile(r'^[1-9]\d{5}$')

EXACT_PINCODE_COORDS = {
    '380001': {'lat': 23.0225, 'lng': 72.5714},  # Ahmedabad Center
    '380013': {'lat': 23.0645, 'lng': 72.5312},  # Naranpura
    '380015': {'lat': 23.0200, 'lng': 72.5100},  # Satellite
    '380051': {'lat': 23.0333, 'lng': 72.5000},  # Jodhpur
    '380052': {'lat': 23.0531, 'lng': 72.5029},  # Bodakdev
    '380054': {'lat': 23.0500, 'lng': 72.5300},  # Memnagar
    '380058': {'lat': 23.0130, 'lng': 72.5410},  # Ambawadi
    '380059': {'lat': 23.0450, 'lng': 72.4890},  # Bopal
    '380061': {'lat': 23.0729, 'lng': 72.5407},  # Ghatlodia
    '380063': {'lat': 23.0600, 'lng': 72.5100},  # Thaltej
    '382421': {'lat': 23.0900, 'lng': 72.5800},  # Motera
    '382424': {'lat': 23.1090, 'lng': 72.5850},  # Sabarmati
    '382481': {'lat': 23.1200, 'lng': 72.5400},  # Chandkheda
    '383001': {'lat': 23.6000, 'lng': 72.9500},  # Himatnagar
    '384240': {'lat': 23.8500, 'lng': 72.3500},  # Patan/Sidhpur
    '110001': {'lat': 28.6353, 'lng': 77.2250},  # Delhi Center
    '110060': {'lat': 28.6430, 'lng': 77.1850},  # Karol Bagh / Delhi
    '400001': {'lat': 18.9220, 'lng': 72.8347},  # Mumbai Center
    '400013': {'lat': 18.9950, 'lng': 72.8250},  # Worli / Mumbai
    '560001': {'lat': 12.9716, 'lng': 77.5946},  # Bangalore Center
    '600001': {'lat': 13.0827, 'lng': 80.2707},  # Chennai Center
    '700001': {'lat': 22.5726, 'lng': 88.3639},  # Kolkata Center
    '500001': {'lat': 17.3850, 'lng': 78.4867},  # Hyderabad Center
}


class DistanceService:
    @staticmethod
    def calculate(lat1, lng1, lat2, lng2):
        """
        Calculate distance between two coordinates in kilometers using Haversine formula.
        """
        if lat1 is None or lng1 is None or lat2 is None or lng2 is None:
            return None
            
        try:
            lat1, lng1, lat2, lng2 = float(lat1), float(lng1), float(lat2), float(lng2)
        except (ValueError, TypeError):
            return None

        earth_radius = 6371.0  # km

        d_lat = math.radians(lat2 - lat1)
        d_lng = math.radians(lng2 - lng1)

        a = (math.sin(d_lat / 2.0) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             (math.sin(d_lng / 2.0) ** 2))

        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

        return round(earth_radius * c, 1)

    @staticmethod
    def get_hardcoded_coordinates(pincode):
        """
        Hardcoded coordinates for major Indian pincodes and regional prefixes.
        Exact pins first; 2-digit/1-digit prefixes only as last-resort regional fallback.
        """
        pincode = str(pincode or '').strip()
        if pincode in EXACT_PINCODE_COORDS:
            return EXACT_PINCODE_COORDS[pincode]
        return DistanceService.get_regional_fallback_coordinates(pincode)

    @staticmethod
    def get_regional_fallback_coordinates(pincode):
        pincode = str(pincode or '').strip()
        prefix_map = {
            '11': {'lat': 28.6139, 'lng': 77.2090},  # Delhi
            '12': {'lat': 29.0588, 'lng': 76.0856},  # Haryana
            '13': {'lat': 30.7333, 'lng': 76.7794},  # Punjab/Chandigarh
            '14': {'lat': 30.7333, 'lng': 76.7794},  # Punjab
            '15': {'lat': 30.3753, 'lng': 76.7821},  # Punjab
            '16': {'lat': 30.7333, 'lng': 76.7794},  # Chandigarh
            '17': {'lat': 31.1048, 'lng': 77.1734},  # Himachal Pradesh
            '18': {'lat': 32.7266, 'lng': 74.8570},  # J&K
            '19': {'lat': 34.0837, 'lng': 74.7973},  # Srinagar
            '20': {'lat': 26.8467, 'lng': 80.9462},  # UP (Lucknow)
            '21': {'lat': 26.4499, 'lng': 80.3319},  # UP (Kanpur)
            '22': {'lat': 26.8467, 'lng': 80.9462},  # UP
            '23': {'lat': 26.8467, 'lng': 80.9462},  # UP
            '24': {'lat': 26.8467, 'lng': 80.9462},  # UP
            '25': {'lat': 28.9845, 'lng': 77.7064},  # UP (Meerut)
            '26': {'lat': 27.1767, 'lng': 78.0081},  # UP (Agra)
            '27': {'lat': 25.3176, 'lng': 82.9739},  # UP (Varanasi)
            '28': {'lat': 26.8467, 'lng': 80.9462},  # UP
            '30': {'lat': 26.9124, 'lng': 75.7873},  # Rajasthan (Jaipur)
            '31': {'lat': 24.5854, 'lng': 73.7125},  # Rajasthan (Udaipur)
            '32': {'lat': 26.2389, 'lng': 73.0243},  # Rajasthan (Jodhpur)
            '33': {'lat': 28.0229, 'lng': 73.3119},  # Rajasthan (Bikaner)
            '34': {'lat': 26.9124, 'lng': 75.7873},  # Rajasthan
            '36': {'lat': 22.3039, 'lng': 70.8022},  # Gujarat (Rajkot)
            '37': {'lat': 21.1702, 'lng': 72.8311},  # Gujarat (Surat)
            '38': {'lat': 23.0225, 'lng': 72.5714},  # Gujarat (Ahmedabad)
            '39': {'lat': 22.3072, 'lng': 73.1812},  # Gujarat (Vadodara)
            '40': {'lat': 18.9220, 'lng': 72.8347},  # Maharashtra (Mumbai)
            '41': {'lat': 18.5204, 'lng': 73.8567},  # Maharashtra (Pune)
            '42': {'lat': 19.9975, 'lng': 73.7898},  # Maharashtra (Nashik)
            '43': {'lat': 19.0760, 'lng': 72.8777},  # Maharashtra
            '44': {'lat': 21.1458, 'lng': 79.0882},  # Maharashtra (Nagpur)
            '45': {'lat': 23.2599, 'lng': 77.4126},  # MP (Bhopal)
            '46': {'lat': 22.7196, 'lng': 75.8577},  # MP (Indore)
            '47': {'lat': 23.1815, 'lng': 79.9864},  # MP (Jabalpur)
            '48': {'lat': 26.2183, 'lng': 78.1828},  # MP (Gwalior)
            '49': {'lat': 21.2514, 'lng': 81.6296},  # Chhattisgarh (Raipur)
            '50': {'lat': 17.3850, 'lng': 78.4867},  # Telangana (Hyderabad)
            '51': {'lat': 17.3850, 'lng': 78.4867},  # Telangana
            '52': {'lat': 17.3850, 'lng': 78.4867},  # Telangana
            '53': {'lat': 16.5062, 'lng': 80.6480},  # AP (Vijayawada)
            '56': {'lat': 12.9716, 'lng': 77.5946},  # Karnataka (Bangalore)
            '57': {'lat': 12.9716, 'lng': 77.5946},  # Karnataka
            '58': {'lat': 15.3647, 'lng': 75.1240},  # Karnataka (Hubli)
            '59': {'lat': 12.9141, 'lng': 74.8560},  # Karnataka (Mangalore)
            '60': {'lat': 13.0827, 'lng': 80.2707},  # Tamil Nadu (Chennai)
            '61': {'lat': 13.0827, 'lng': 80.2707},  # Tamil Nadu
            '62': {'lat': 9.9252, 'lng': 78.1198},  # Tamil Nadu (Madurai)
            '63': {'lat': 11.0168, 'lng': 76.9558},  # Tamil Nadu (Coimbatore)
            '64': {'lat': 13.0827, 'lng': 80.2707},  # Tamil Nadu
            '67': {'lat': 8.5241, 'lng': 76.9366},  # Kerala (Trivandrum)
            '68': {'lat': 9.9312, 'lng': 76.2673},  # Kerala (Kochi)
            '69': {'lat': 11.2588, 'lng': 75.7804},  # Kerala (Calicut)
            '70': {'lat': 22.5726, 'lng': 88.3639},  # West Bengal (Kolkata)
            '71': {'lat': 22.5726, 'lng': 88.3639},  # West Bengal
            '72': {'lat': 22.5726, 'lng': 88.3639},  # West Bengal
            '73': {'lat': 26.7271, 'lng': 88.3953},  # West Bengal (Siliguri)
            '74': {'lat': 22.5726, 'lng': 88.3639},  # West Bengal
            '75': {'lat': 20.2961, 'lng': 85.8245},  # Odisha (Bhubaneswar)
            '76': {'lat': 20.4625, 'lng': 85.8830},  # Odisha (Cuttack)
            '78': {'lat': 26.1445, 'lng': 91.7362},  # Assam (Guwahati)
            '79': {'lat': 23.8315, 'lng': 91.2868},  # Tripura/Manipur/Nagaland
            '80': {'lat': 25.5941, 'lng': 85.1376},  # Bihar (Patna)
            '81': {'lat': 25.5941, 'lng': 85.1376},  # Bihar
            '82': {'lat': 25.5941, 'lng': 85.1376},  # Bihar
            '83': {'lat': 23.3441, 'lng': 85.3096},  # Jharkhand (Ranchi)
            '84': {'lat': 23.3441, 'lng': 85.3096},  # Jharkhand
            '85': {'lat': 23.3441, 'lng': 85.3096},  # Jharkhand
        }

        prefix = pincode[:2]
        if prefix in prefix_map:
            return prefix_map[prefix]

        major_region = pincode[:1]
        region_map = {
            '1': {'lat': 28.6139, 'lng': 77.2090},  # Delhi/North
            '2': {'lat': 26.8467, 'lng': 80.9462},  # UP/North
            '3': {'lat': 23.0225, 'lng': 72.5714},  # Gujarat/West
            '4': {'lat': 19.0760, 'lng': 72.8777},  # Maharashtra/West
            '5': {'lat': 12.9716, 'lng': 77.5946},  # Karnataka/South
            '6': {'lat': 13.0827, 'lng': 80.2707},  # Tamil Nadu/South
            '7': {'lat': 22.5726, 'lng': 88.3639},  # WB/East
            '8': {'lat': 25.5941, 'lng': 85.1376},  # Bihar/East
        }
        return region_map.get(major_region)

    @classmethod
    def get_pincode_coordinates(cls, pincode):
        """
        Resolve coordinates for a pincode: exact hardcoded → local DB → regional fallback.
        Prefix fallbacks must not run before the database, or every 38xxxx pin maps to Ahmedabad.
        """
        pincode = str(pincode or '').strip()
        if not pincode:
            return None

        exact = EXACT_PINCODE_COORDS.get(pincode)
        if exact:
            return exact

        try:
            record = Pincode.objects.filter(pincode=pincode).first()
            if record and record.latitude and record.longitude:
                return {
                    'lat': float(record.latitude),
                    'lng': float(record.longitude)
                }
        except Exception as e:
            logger.warning(f"DistanceService.get_pincode_coordinates database lookup failed: {e}")

        return cls.get_regional_fallback_coordinates(pincode)

    @staticmethod
    def get_city_coordinates(city):
        """
        Get coordinates for a given city name.
        """
        city = str(city).strip().lower()
        cities = {
            'ahmedabad': {'lat': 23.0225, 'lng': 72.5714},
            'mumbai': {'lat': 18.9220, 'lng': 72.8347},
            'surat': {'lat': 21.1702, 'lng': 72.8311},
            'rajkot': {'lat': 22.3039, 'lng': 70.8022},
            'vadodara': {'lat': 22.3072, 'lng': 73.1812},
            'gandhinagar': {'lat': 23.2156, 'lng': 72.6369},
            'patan': {'lat': 23.8500, 'lng': 72.1200},
            'mehsana': {'lat': 23.5880, 'lng': 72.3693},
            'delhi': {'lat': 28.6139, 'lng': 77.2090},
            'new delhi': {'lat': 28.6139, 'lng': 77.2090},
            'bangalore': {'lat': 12.9716, 'lng': 77.5946},
            'bengaluru': {'lat': 12.9716, 'lng': 77.5946},
            'pune': {'lat': 18.5204, 'lng': 73.8567},
            'hyderabad': {'lat': 17.3850, 'lng': 78.4867},
            'chennai': {'lat': 13.0827, 'lng': 80.2707},
            'kolkata': {'lat': 22.5726, 'lng': 88.3639},
            'jaipur': {'lat': 26.9124, 'lng': 75.7873},
            'lucknow': {'lat': 26.8467, 'lng': 80.9462},
            'kanpur': {'lat': 26.4499, 'lng': 80.3319},
            'nagpur': {'lat': 21.1458, 'lng': 79.0882},
            'indore': {'lat': 22.7196, 'lng': 75.8577},
            'bhopal': {'lat': 23.2599, 'lng': 77.4126},
            'chandigarh': {'lat': 30.7333, 'lng': 76.7794},
        }
        return cities.get(city)


def _normalize_pin(value):
    pin = str(value or '').strip()
    return pin if _PIN_RE.match(pin) else ''


def iter_agent_service_pincodes(agent):
    """Collect every 6-digit pin this agent covers (profile JSON + servicePincodes table)."""
    pins = []
    seen = set()

    def add(value):
        pin = _normalize_pin(value)
        if pin and pin not in seen:
            seen.add(pin)
            pins.append(pin)

    add(getattr(agent, 'agent_pincode', None))

    profile = getattr(agent, 'profile', None)
    raw = getattr(profile, 'service_pincodes', None) if profile else None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            raw = [raw]
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                add(item.get('pincode') or item.get('pin') or item.get('service_pincode'))
            else:
                add(item)

    try:
        for row in agent.servicePincodes.all():
            add(getattr(row, 'service_pincode', None))
    except Exception:
        pass

    return pins


def agent_serves_pincode(agent, pincode):
    target = _normalize_pin(pincode)
    if not target:
        return False
    return target in iter_agent_service_pincodes(agent)


def apply_search_proximity(agents, user_lat, user_lng, search_pincode=None, radius_km=50):
    """
    Attach .distance and keep agents who either:
    - explicitly service the searched pincode, or
    - are within radius_km of the search coordinates.
    """
    search_pin = _normalize_pin(search_pincode)
    filtered = []

    for agent in agents:
        serves = bool(search_pin) and agent_serves_pincode(agent, search_pin)
        agent.serves_search_pincode = serves
        agent.distance = None

        if serves:
            agent.distance = 0
            filtered.append(agent)
            continue

        if user_lat is None or user_lng is None:
            filtered.append(agent)
            continue

        best = None
        if agent.latitude and agent.longitude:
            best = DistanceService.calculate(user_lat, user_lng, agent.latitude, agent.longitude)

        for pin in iter_agent_service_pincodes(agent):
            coords = DistanceService.get_pincode_coordinates(pin)
            if not coords:
                continue
            dist = DistanceService.calculate(user_lat, user_lng, coords['lat'], coords['lng'])
            if dist is None:
                continue
            if best is None or dist < best:
                best = dist

        if best is None:
            profile = getattr(agent, 'profile', None)
            if profile:
                first_city = agent.serviceableCities.first() if hasattr(agent, 'serviceableCities') else None
                if first_city:
                    city_coords = DistanceService.get_city_coordinates(first_city.name)
                    if city_coords:
                        best = DistanceService.calculate(
                            user_lat, user_lng, city_coords['lat'], city_coords['lng']
                        )

        agent.distance = best if best is not None else 999999
        if agent.distance <= radius_km:
            filtered.append(agent)

    return filtered
