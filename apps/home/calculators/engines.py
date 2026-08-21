"""Python formula engines for public financial calculators.

JS twins live in static/js/calculators/engines.js — keep them in sync.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict


def _round_inr(value: float) -> int:
    if not math.isfinite(value):
        return 0
    return int(round(value))


def _monthly_rate(annual_rate: float) -> float:
    return float(annual_rate) / 100.0 / 12.0


def sip(monthly_amount: float, years: float, annual_rate: float, **_kwargs) -> Dict[str, Any]:
    """Future value of a monthly SIP (annuity due)."""
    p = float(monthly_amount)
    n = int(round(float(years) * 12))
    r = _monthly_rate(annual_rate)
    invested = p * n
    if n <= 0:
        fv = 0.0
    elif abs(r) < 1e-12:
        fv = invested
    else:
        fv = p * (((1 + r) ** n - 1) / r) * (1 + r)
    fv = max(fv, 0.0)
    gain = max(fv - invested, 0.0)
    return {
        'future_value': _round_inr(fv),
        'invested': _round_inr(invested),
        'gain': _round_inr(gain),
        'primary': _round_inr(fv),
    }


def goal_sip(target_amount: float, years: float, annual_rate: float, **_kwargs) -> Dict[str, Any]:
    """Required monthly SIP to reach a target corpus."""
    fv = float(target_amount)
    n = int(round(float(years) * 12))
    r = _monthly_rate(annual_rate)
    if n <= 0:
        p = fv
    elif abs(r) < 1e-12:
        p = fv / n
    else:
        p = fv * r / (((1 + r) ** n - 1) * (1 + r))
    p = max(p, 0.0)
    invested = p * n
    gain = max(fv - invested, 0.0)
    return {
        'monthly_sip': _round_inr(p),
        'target_amount': _round_inr(fv),
        'invested': _round_inr(invested),
        'gain': _round_inr(gain),
        'primary': _round_inr(p),
    }


def step_up_sip(monthly_amount: float, years: float, annual_rate: float, step_up_percent: float, **_kwargs) -> Dict[str, Any]:
    """SIP that increases by step_up_percent at the end of each year."""
    monthly = float(monthly_amount)
    years_i = int(round(float(years)))
    r = _monthly_rate(annual_rate)
    step = float(step_up_percent) / 100.0
    fv = 0.0
    invested = 0.0
    for _year in range(max(years_i, 0)):
        for _month in range(12):
            invested += monthly
            fv = (fv + monthly) * (1 + r)
        monthly *= (1 + step)
    fv = max(fv, 0.0)
    gain = max(fv - invested, 0.0)
    return {
        'future_value': _round_inr(fv),
        'invested': _round_inr(invested),
        'gain': _round_inr(gain),
        'primary': _round_inr(fv),
    }


def lumpsum(amount: float, years: float, annual_rate: float, **_kwargs) -> Dict[str, Any]:
    """Lumpsum compounded monthly."""
    p = float(amount)
    n = int(round(float(years) * 12))
    r = _monthly_rate(annual_rate)
    fv = p * ((1 + r) ** n) if n > 0 else p
    fv = max(fv, 0.0)
    gain = max(fv - p, 0.0)
    return {
        'future_value': _round_inr(fv),
        'invested': _round_inr(p),
        'gain': _round_inr(gain),
        'primary': _round_inr(fv),
    }


def emi(loan_amount: float, years: float, annual_rate: float, **_kwargs) -> Dict[str, Any]:
    """Reducing-balance EMI."""
    p = float(loan_amount)
    n = int(round(float(years) * 12))
    r = _monthly_rate(annual_rate)
    if n <= 0:
        instalment = p
    elif abs(r) < 1e-12:
        instalment = p / n
    else:
        instalment = p * r * ((1 + r) ** n) / (((1 + r) ** n) - 1)
    total_payment = instalment * n
    total_interest = max(total_payment - p, 0.0)
    return {
        'emi': _round_inr(instalment),
        'principal': _round_inr(p),
        'total_payment': _round_inr(total_payment),
        'total_interest': _round_inr(total_interest),
        'primary': _round_inr(instalment),
    }


def compound_interest(principal: float, years: float, annual_rate: float, frequency: float = 4, **_kwargs) -> Dict[str, Any]:
    """Compound interest with selectable compounding frequency per year."""
    p = float(principal)
    t = float(years)
    rate = float(annual_rate) / 100.0
    n = max(int(round(float(frequency))), 1)
    fv = p * ((1 + rate / n) ** (n * t)) if t > 0 else p
    fv = max(fv, 0.0)
    gain = max(fv - p, 0.0)
    return {
        'future_value': _round_inr(fv),
        'invested': _round_inr(p),
        'gain': _round_inr(gain),
        'primary': _round_inr(fv),
    }


def inflation(current_amount: float, years: float, inflation_rate: float, **_kwargs) -> Dict[str, Any]:
    """Future cost of a present amount at a constant inflation rate."""
    p = float(current_amount)
    t = float(years)
    i = float(inflation_rate) / 100.0
    future = p * ((1 + i) ** t) if t > 0 else p
    extra = max(future - p, 0.0)
    return {
        'future_cost': _round_inr(future),
        'current_amount': _round_inr(p),
        'extra_needed': _round_inr(extra),
        'primary': _round_inr(future),
    }


def fd(amount: float, years: float, annual_rate: float, frequency: float = 4, **_kwargs) -> Dict[str, Any]:
    """Fixed deposit maturity (India default: quarterly compounding)."""
    return compound_interest(amount, years, annual_rate, frequency)


def ppf(annual_amount: float, years: float, annual_rate: float, **_kwargs) -> Dict[str, Any]:
    """PPF-style yearly contribution compounded annually (educational)."""
    p = float(annual_amount)
    n = int(round(float(years)))
    r = float(annual_rate) / 100.0
    invested = p * n
    if n <= 0:
        fv = 0.0
    elif abs(r) < 1e-12:
        fv = invested
    else:
        # Contribution at end of each year (ordinary annuity)
        fv = p * (((1 + r) ** n - 1) / r)
    fv = max(fv, 0.0)
    gain = max(fv - invested, 0.0)
    return {
        'future_value': _round_inr(fv),
        'invested': _round_inr(invested),
        'gain': _round_inr(gain),
        'primary': _round_inr(fv),
    }


def human_life_value(
    annual_income: float,
    years_to_retire: float,
    existing_savings: float = 0,
    **_kwargs,
) -> Dict[str, Any]:
    """Educational HLV: income × years to retire − existing savings."""
    cover = float(annual_income) * float(years_to_retire) - float(existing_savings)
    cover = max(cover, 0.0)
    return {
        'cover_needed': _round_inr(cover),
        'income_stream': _round_inr(float(annual_income) * float(years_to_retire)),
        'existing_savings': _round_inr(float(existing_savings)),
        'primary': _round_inr(cover),
    }


def insurance_premium(
    calc_type: str = 'health',
    age: float = 25,
    gender: str = 'male',
    coverage: float = 500000,
    term: float = 15,
    smoking: str = 'no',
    **_kwargs,
) -> Dict[str, Any]:
    """Educational premium estimate (not an insurer quote)."""
    base_rate = 0.01
    if calc_type == 'life':
        base_rate = 0.005
    elif calc_type == 'general':
        base_rate = 0.003
    age_factor = 1 + (float(age) - 20) * 0.03
    smoking_m = 1.4 if smoking == 'yes' else 1.0
    gender_m = 0.95 if gender == 'female' else 1.0
    type_m = 1.2 if calc_type == 'health' else 1.0
    annual = float(coverage) * base_rate * age_factor * smoking_m * gender_m * type_m
    annual = annual * (1 - (float(term) / 100.0))
    annual = max(annual, 0.0)
    monthly = annual / 12.0
    return {
        'yearly_premium': _round_inr(annual),
        'monthly_premium': _round_inr(monthly),
        'coverage': _round_inr(float(coverage)),
        'primary': _round_inr(monthly),
    }


def swp(amount: float, monthly_withdrawal: float, years: float, annual_rate: float, **_kwargs) -> Dict[str, Any]:
    """Grow a corpus monthly and withdraw a fixed amount."""
    balance = float(amount)
    w = float(monthly_withdrawal)
    n = int(round(float(years) * 12))
    r = _monthly_rate(annual_rate)
    withdrawn = 0.0
    for _ in range(max(n, 0)):
        balance = balance * (1 + r) - w
        if balance < 0:
            withdrawn += w + balance
            balance = 0.0
            break
        withdrawn += w
    remaining = max(balance, 0.0)
    return {
        'remaining': _round_inr(remaining),
        'total_withdrawn': _round_inr(max(withdrawn, 0.0)),
        'invested': _round_inr(float(amount)),
        'primary': _round_inr(remaining),
    }


def nps(monthly_amount: float, years: float, annual_rate: float, **_kwargs) -> Dict[str, Any]:
    """NPS corpus via SIP, with 60% lump and 40% annuity at 6%."""
    result = sip(monthly_amount, years, annual_rate)
    corpus = result['future_value']
    lump = corpus * 0.60
    annuity_corpus = corpus * 0.40
    yearly_pension = annuity_corpus * 0.06
    return {
        'future_value': corpus,
        'invested': result['invested'],
        'gain': result['gain'],
        'lump_sum': _round_inr(lump),
        'annuity_corpus': _round_inr(annuity_corpus),
        'yearly_pension': _round_inr(yearly_pension),
        'primary': corpus,
    }


def retirement(
    monthly_expense: float,
    years_to_retire: float,
    retirement_years: float,
    inflation_rate: float,
    annual_rate: float,
    **_kwargs,
) -> Dict[str, Any]:
    """Corpus needed for inflation-adjusted retirement spending."""
    future_expense = float(monthly_expense) * ((1 + float(inflation_rate) / 100.0) ** float(years_to_retire))
    n = int(round(float(retirement_years) * 12))
    r = _monthly_rate(annual_rate)
    if n <= 0:
        corpus = 0.0
    elif abs(r) < 1e-12:
        corpus = future_expense * n
    else:
        corpus = future_expense * (1 - (1 + r) ** (-n)) / r
    sip_needed = goal_sip(corpus, years_to_retire, annual_rate)
    return {
        'corpus_needed': _round_inr(corpus),
        'future_expense': _round_inr(future_expense),
        'monthly_sip': sip_needed['monthly_sip'],
        'primary': _round_inr(corpus),
    }


def pension(monthly_pension: float, years: float, annual_rate: float, **_kwargs) -> Dict[str, Any]:
    """Required SIP to fund a 20-year pension at the given return."""
    pmt = float(monthly_pension)
    r = _monthly_rate(annual_rate)
    n_payout = 20 * 12
    if abs(r) < 1e-12:
        corpus = pmt * n_payout
    else:
        corpus = pmt * (1 - (1 + r) ** (-n_payout)) / r
    needed = goal_sip(corpus, years, annual_rate)
    return {
        'monthly_sip': needed['monthly_sip'],
        'corpus_needed': _round_inr(corpus),
        'invested': needed['invested'],
        'gain': needed['gain'],
        'primary': needed['monthly_sip'],
    }


def epf(monthly_amount: float, years: float, annual_rate: float, **_kwargs) -> Dict[str, Any]:
    return sip(monthly_amount, years, annual_rate)


def rd(monthly_amount: float, years: float, annual_rate: float, **_kwargs) -> Dict[str, Any]:
    """RD as an ordinary monthly annuity (end of month)."""
    p = float(monthly_amount)
    n = int(round(float(years) * 12))
    r = _monthly_rate(annual_rate)
    invested = p * n
    if n <= 0:
        fv = 0.0
    elif abs(r) < 1e-12:
        fv = invested
    else:
        fv = p * (((1 + r) ** n - 1) / r)
    fv = max(fv, 0.0)
    return {
        'future_value': _round_inr(fv),
        'invested': _round_inr(invested),
        'gain': _round_inr(max(fv - invested, 0.0)),
        'primary': _round_inr(fv),
    }


def gratuity(monthly_salary: float, years: float, **_kwargs) -> Dict[str, Any]:
    """Payment of Gratuity Act: 15/26 × last salary × years, capped at ₹20 lakh."""
    years_i = max(int(float(years)), 0)
    uncapped = (15.0 / 26.0) * float(monthly_salary) * years_i
    cap = 2000000.0
    amount = min(max(uncapped, 0.0), cap)
    return {
        'gratuity': _round_inr(amount),
        'uncapped': _round_inr(max(uncapped, 0.0)),
        'statutory_cap': _round_inr(cap),
        'primary': _round_inr(amount),
    }


def cost_of_delay(monthly_amount: float, years: float, delay_years: float, annual_rate: float, **_kwargs) -> Dict[str, Any]:
    delay = min(float(delay_years), float(years))
    start_now = sip(monthly_amount, years, annual_rate)
    delayed = sip(monthly_amount, max(float(years) - delay, 0), annual_rate)
    cost = max(start_now['future_value'] - delayed['future_value'], 0)
    return {
        'cost': cost,
        'start_now': start_now['future_value'],
        'delayed_value': delayed['future_value'],
        'primary': cost,
    }


def power_of_compounding(monthly_amount: float, years: float, annual_rate: float, **_kwargs) -> Dict[str, Any]:
    return sip(monthly_amount, years, annual_rate)


def future_value(amount: float, years: float, annual_rate: float, **_kwargs) -> Dict[str, Any]:
    return lumpsum(amount, years, annual_rate)


def increasing_contribution(
    monthly_amount: float, years: float, annual_rate: float, step_up_percent: float, **_kwargs
) -> Dict[str, Any]:
    return step_up_sip(monthly_amount, years, annual_rate, step_up_percent)


def bond_yield(face_value: float, price: float, coupon: float, **_kwargs) -> Dict[str, Any]:
    face = float(face_value)
    px = max(float(price), 0.01)
    coupon_income = face * float(coupon) / 100.0
    current = coupon_income / px * 100.0
    return {
        'current_yield': round(current, 2),
        'coupon_income': _round_inr(coupon_income),
        'price': _round_inr(px),
        'primary': round(current, 2),
    }


def annuity_payout(amount: float, years: float, annual_rate: float, **_kwargs) -> Dict[str, Any]:
    p = float(amount)
    n = int(round(float(years) * 12))
    r = _monthly_rate(annual_rate)
    if n <= 0:
        pmt = p
    elif abs(r) < 1e-12:
        pmt = p / n
    else:
        pmt = p * r / (1 - (1 + r) ** (-n))
    yearly = pmt * 12
    total = pmt * n
    return {
        'monthly_payout': _round_inr(pmt),
        'yearly_payout': _round_inr(yearly),
        'total_payout': _round_inr(total),
        'invested': _round_inr(p),
        'primary': _round_inr(pmt),
    }


def net_worth(assets: float, liabilities: float, **_kwargs) -> Dict[str, Any]:
    a = float(assets)
    l = float(liabilities)
    nw = a - l
    return {
        'net_worth': _round_inr(nw),
        'assets': _round_inr(a),
        'liabilities': _round_inr(l),
        'primary': _round_inr(nw),
    }


def asset_allocation(age: float, amount: float, **_kwargs) -> Dict[str, Any]:
    """Rule of thumb: equity ≈ 100 − age (floored 20%, capped 80%), 10% other, rest debt."""
    equity_pct = min(max(100.0 - float(age), 20.0), 80.0)
    other_pct = 10.0
    debt_pct = max(100.0 - equity_pct - other_pct, 0.0)
    total = float(amount)
    equity = total * equity_pct / 100.0
    debt = total * debt_pct / 100.0
    other = total * other_pct / 100.0
    return {
        'equity': _round_inr(equity),
        'debt': _round_inr(debt),
        'other': _round_inr(other),
        'primary': _round_inr(equity),
    }


def present_value(future_amount: float, years: float, annual_rate: float, **_kwargs) -> Dict[str, Any]:
    fv = float(future_amount)
    t = float(years)
    rate = float(annual_rate) / 100.0
    pv = fv / ((1 + rate) ** t) if t > 0 else fv
    discount = max(fv - pv, 0.0)
    return {
        'present_value': _round_inr(pv),
        'future_amount': _round_inr(fv),
        'discount': _round_inr(discount),
        'primary': _round_inr(pv),
    }


def income_tax(annual_income: float, **_kwargs) -> Dict[str, Any]:
    """New tax regime FY 2025-26 slabs + 87A rebate up to ₹12 lakh, plus 4% cess."""
    income = max(float(annual_income), 0.0)
    slabs = [
        (400000, 0.00),
        (800000, 0.05),
        (1200000, 0.10),
        (1600000, 0.15),
        (2000000, 0.20),
        (2400000, 0.25),
        (float('inf'), 0.30),
    ]
    tax = 0.0
    lower = 0.0
    for upper, rate in slabs:
        band = min(income, upper) - lower
        if band > 0:
            tax += band * rate
        if income <= upper:
            break
        lower = upper
    if income <= 1200000:
        tax = max(tax - 60000.0, 0.0)
    cess = tax * 0.04
    total = tax + cess
    return {
        'tax_before_cess': _round_inr(tax),
        'cess': _round_inr(cess),
        'total_tax': _round_inr(total),
        'take_home': _round_inr(income - total),
        'primary': _round_inr(total),
    }


def hra(basic: float, hra_received: float, rent_paid: float, city_type: str = 'metro', **_kwargs) -> Dict[str, Any]:
    basic_a = float(basic)
    received = float(hra_received)
    rent = float(rent_paid)
    pct = 0.50 if city_type == 'metro' else 0.40
    exemption = min(received, max(rent - 0.10 * basic_a, 0.0), pct * basic_a)
    exemption = max(exemption, 0.0)
    return {
        'exemption': _round_inr(exemption),
        'taxable_hra': _round_inr(max(received - exemption, 0.0)),
        'hra_received': _round_inr(received),
        'primary': _round_inr(exemption),
    }


def _parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or '').strip()[:10]
    if not text:
        return date.today()
    try:
        return datetime.strptime(text, '%Y-%m-%d').date()
    except ValueError:
        return date.today()


def _fmt_date(value: date) -> str:
    return value.isoformat()


def health_insurance(
    age: float = 30,
    gender: str = 'male',
    coverage: float = 500000,
    term: float = 1,
    smoking: str = 'no',
    members: float = 1,
    **_kwargs,
) -> Dict[str, Any]:
    base = insurance_premium('health', age, gender, coverage, max(term, 1), smoking)
    extra = max(float(members) - 1.0, 0.0)
    yearly = base['yearly_premium'] * (1 + 0.35 * extra)
    return {
        'yearly_premium': _round_inr(yearly),
        'monthly_premium': _round_inr(yearly / 12.0),
        'coverage': _round_inr(float(coverage)),
        'primary': _round_inr(yearly / 12.0),
    }


def life_insurance(
    age: float = 30,
    gender: str = 'male',
    coverage: float = 5000000,
    term: float = 20,
    smoking: str = 'no',
    **_kwargs,
) -> Dict[str, Any]:
    return insurance_premium('life', age, gender, coverage, term, smoking)


def term_insurance(
    age: float = 30,
    gender: str = 'male',
    coverage: float = 10000000,
    term: float = 30,
    smoking: str = 'no',
    **_kwargs,
) -> Dict[str, Any]:
    result = insurance_premium('life', age, gender, coverage, term, smoking)
    yearly = result['yearly_premium'] * 0.85
    return {
        'yearly_premium': _round_inr(yearly),
        'monthly_premium': _round_inr(yearly / 12.0),
        'coverage': _round_inr(float(coverage)),
        'primary': _round_inr(yearly / 12.0),
    }


def lic_calculator(age: float, coverage: float, term: float, **_kwargs) -> Dict[str, Any]:
    sa = float(coverage)
    years = max(float(term), 1.0)
    age_f = max(float(age), 18.0)
    yearly = (sa / 1000.0) * (18.0 + age_f / 8.0)
    bonus = sa * 0.045 * years
    maturity = sa + bonus
    return {
        'yearly_premium': _round_inr(yearly),
        'monthly_premium': _round_inr(yearly / 12.0),
        'maturity': _round_inr(maturity),
        'bonus': _round_inr(bonus),
        'coverage': _round_inr(sa),
        'primary': _round_inr(yearly),
    }


def ulip_calculator(
    monthly_amount: float,
    years: float,
    annual_rate: float,
    charge_percent: float = 2.25,
    **_kwargs,
) -> Dict[str, Any]:
    net = max(float(annual_rate) - float(charge_percent), 0.0)
    result = sip(monthly_amount, years, net)
    charges = sip(monthly_amount, years, annual_rate)
    charge_drag = max(charges['future_value'] - result['future_value'], 0)
    return {
        'future_value': result['future_value'],
        'invested': result['invested'],
        'gain': result['gain'],
        'charge_drag': charge_drag,
        'primary': result['future_value'],
    }


def home_loan_insurance(loan_amount: float, years: float, annual_rate: float = 8.5, **_kwargs) -> Dict[str, Any]:
    outstanding = float(loan_amount)
    cover = max(outstanding, 0.0)
    yearly = cover * 0.0035 * (1 + float(years) / 40.0)
    return {
        'cover_needed': _round_inr(cover),
        'yearly_premium': _round_inr(yearly),
        'monthly_premium': _round_inr(yearly / 12.0),
        'outstanding': _round_inr(outstanding),
        'primary': _round_inr(cover),
    }


def _motor_premium(idv: float, vehicle_age: float, ncb_percent: float, od_rate: float, tp: float) -> Dict[str, Any]:
    age = max(float(vehicle_age), 0.0)
    ncb = min(max(float(ncb_percent), 0.0), 50.0) / 100.0
    od = float(idv) * (od_rate + age * 0.002) * (1.0 - ncb)
    od = max(od, 0.0)
    total = od + tp
    return {
        'od_premium': _round_inr(od),
        'tp_premium': _round_inr(tp),
        'yearly_premium': _round_inr(total),
        'idv': _round_inr(float(idv)),
        'primary': _round_inr(total),
    }


def car_insurance(idv: float, vehicle_age: float, ncb_percent: float = 0, **_kwargs) -> Dict[str, Any]:
    return _motor_premium(idv, vehicle_age, ncb_percent, 0.025, 2094)


def bike_insurance(idv: float, vehicle_age: float, ncb_percent: float = 0, **_kwargs) -> Dict[str, Any]:
    return _motor_premium(idv, vehicle_age, ncb_percent, 0.035, 714)


def idv_calculator(ex_showroom: float, vehicle_age: float, **_kwargs) -> Dict[str, Any]:
    price = float(ex_showroom)
    age = max(float(vehicle_age), 0.0)
    if age <= 0.5:
        dep = 0.05
    elif age <= 1:
        dep = 0.15
    elif age <= 2:
        dep = 0.20
    elif age <= 3:
        dep = 0.30
    elif age <= 4:
        dep = 0.40
    elif age <= 5:
        dep = 0.50
    else:
        dep = min(0.50 + 0.05 * (age - 5.0), 0.80)
    idv = price * (1.0 - dep)
    return {
        'idv': _round_inr(idv),
        'depreciation': _round_inr(price - idv),
        'ex_showroom': _round_inr(price),
        'primary': _round_inr(idv),
    }


def travel_insurance(
    trip_days: float,
    travellers: float,
    coverage: float,
    destination_type: str = 'asia',
    **_kwargs,
) -> Dict[str, Any]:
    dest_m = {'domestic': 0.6, 'asia': 1.0, 'worldwide': 1.6}.get(str(destination_type), 1.0)
    days = max(float(trip_days), 1.0)
    people = max(float(travellers), 1.0)
    cover = float(coverage)
    premium = days * people * dest_m * (cover / 100000.0) * 45.0
    return {
        'yearly_premium': _round_inr(premium),
        'per_person': _round_inr(premium / people),
        'coverage': _round_inr(cover),
        'primary': _round_inr(premium),
    }


def ssy(annual_amount: float, years: float = 21, annual_rate: float = 8.2, **_kwargs) -> Dict[str, Any]:
    n = min(max(int(round(float(years))), 1), 21)
    return ppf(min(float(annual_amount), 150000.0), n, annual_rate)


def savings_calculator(amount: float, years: float, annual_rate: float, **_kwargs) -> Dict[str, Any]:
    return compound_interest(amount, years, annual_rate, 4)


def section_80d(
    self_premium: float,
    parents_premium: float,
    self_senior: str = 'no',
    parents_senior: str = 'no',
    preventive: float = 0,
    **_kwargs,
) -> Dict[str, Any]:
    self_cap = 50000.0 if self_senior == 'yes' else 25000.0
    parent_cap = 50000.0 if parents_senior == 'yes' else 25000.0
    prev = min(max(float(preventive), 0.0), 5000.0)
    self_ded = min(max(float(self_premium), 0.0) + prev, self_cap)
    parent_ded = min(max(float(parents_premium), 0.0), parent_cap)
    total = self_ded + parent_ded
    return {
        'total_deduction': _round_inr(total),
        'self_deduction': _round_inr(self_ded),
        'parents_deduction': _round_inr(parent_ded),
        'primary': _round_inr(total),
    }


def ulip_vs_mutual_fund(
    monthly_amount: float,
    years: float,
    ulip_rate: float,
    mf_rate: float,
    charge_percent: float = 2.25,
    term_premium: float = 800,
    **_kwargs,
) -> Dict[str, Any]:
    ulip = ulip_calculator(monthly_amount, years, ulip_rate, charge_percent)
    mf = sip(monthly_amount, years, mf_rate)
    term_cost = float(term_premium) * 12 * float(years)
    term_plus_sip = max(mf['future_value'] - _round_inr(term_cost), 0)
    return {
        'ulip_value': ulip['future_value'],
        'mf_value': mf['future_value'],
        'term_plus_sip': term_plus_sip,
        'difference': _round_inr(term_plus_sip - ulip['future_value']),
        'primary': term_plus_sip,
    }


def endowment_vs_mutual_fund(
    monthly_amount: float,
    years: float,
    endowment_rate: float = 5,
    mf_rate: float = 12,
    term_premium: float = 800,
    **_kwargs,
) -> Dict[str, Any]:
    endw = sip(monthly_amount, years, endowment_rate)
    mf = sip(monthly_amount, years, mf_rate)
    term_cost = float(term_premium) * 12 * float(years)
    term_plus_sip = max(mf['future_value'] - _round_inr(term_cost), 0)
    return {
        'endowment_value': endw['future_value'],
        'mf_value': mf['future_value'],
        'term_plus_sip': term_plus_sip,
        'difference': _round_inr(term_plus_sip - endw['future_value']),
        'primary': term_plus_sip,
    }


def family_floater_vs_individual(
    members: float,
    age: float,
    coverage: float,
    **_kwargs,
) -> Dict[str, Any]:
    n = max(float(members), 1.0)
    floater = health_insurance(age=age, coverage=coverage, members=n)
    individual = health_insurance(age=age, coverage=coverage, members=1)
    individual_total = individual['yearly_premium'] * n
    return {
        'floater_premium': floater['yearly_premium'],
        'individual_premium': _round_inr(individual_total),
        'savings': _round_inr(max(individual_total - floater['yearly_premium'], 0)),
        'primary': floater['yearly_premium'],
    }


def super_top_up(base_cover: float, extra_cover: float, deductible: float, age: float, **_kwargs) -> Dict[str, Any]:
    age_f = 1 + (float(age) - 20) * 0.025
    yearly = float(extra_cover) * 0.0018 * age_f
    return {
        'yearly_premium': _round_inr(yearly),
        'total_cover': _round_inr(float(base_cover) + float(extra_cover)),
        'deductible': _round_inr(float(deductible)),
        'primary': _round_inr(yearly),
    }


def life_cover_calculator(
    annual_income: float,
    years_to_retire: float,
    liabilities: float = 0,
    existing_cover: float = 0,
    **_kwargs,
) -> Dict[str, Any]:
    need = float(annual_income) * float(years_to_retire) + float(liabilities) - float(existing_cover)
    need = max(need, 0.0)
    return {
        'cover_needed': _round_inr(need),
        'income_stream': _round_inr(float(annual_income) * float(years_to_retire)),
        'liabilities': _round_inr(float(liabilities)),
        'existing_cover': _round_inr(float(existing_cover)),
        'primary': _round_inr(need),
    }


def critical_illness_cover(age: float, coverage: float, **_kwargs) -> Dict[str, Any]:
    age_f = 1 + (float(age) - 20) * 0.04
    yearly = float(coverage) * 0.007 * age_f
    return {
        'yearly_premium': _round_inr(yearly),
        'monthly_premium': _round_inr(yearly / 12.0),
        'coverage': _round_inr(float(coverage)),
        'primary': _round_inr(yearly),
    }


def sip_vs_lumpsum(monthly_amount: float, years: float, annual_rate: float, **_kwargs) -> Dict[str, Any]:
    sip_r = sip(monthly_amount, years, annual_rate)
    lump_amount = float(monthly_amount) * 12 * float(years)
    lump = lumpsum(lump_amount, years, annual_rate)
    return {
        'sip_value': sip_r['future_value'],
        'lumpsum_value': lump['future_value'],
        'sip_invested': sip_r['invested'],
        'lumpsum_invested': lump['invested'],
        'primary': sip_r['future_value'],
    }


def bmi_calculator(weight_kg: float, height_cm: float, **_kwargs) -> Dict[str, Any]:
    h = max(float(height_cm), 1.0) / 100.0
    bmi = float(weight_kg) / (h * h)
    if bmi < 18.5:
        category = 'Underweight'
    elif bmi < 25:
        category = 'Normal'
    elif bmi < 30:
        category = 'Overweight'
    else:
        category = 'Obese'
    return {
        'bmi': round(bmi, 1),
        'category': category,
        'weight_kg': round(float(weight_kg), 1),
        'primary': round(bmi, 1),
    }


def ideal_weight_calculator(height_cm: float, gender: str = 'male', **_kwargs) -> Dict[str, Any]:
    inches = float(height_cm) / 2.54
    over = max(inches - 60.0, 0.0)
    if gender == 'female':
        ideal = 45.5 + 2.3 * over
    else:
        ideal = 50.0 + 2.3 * over
    return {
        'ideal_weight': round(ideal, 1),
        'height_cm': round(float(height_cm), 1),
        'primary': round(ideal, 1),
    }


def bmr_calculator(weight_kg: float, height_cm: float, age: float, gender: str = 'male', **_kwargs) -> Dict[str, Any]:
    if gender == 'female':
        bmr = 10 * float(weight_kg) + 6.25 * float(height_cm) - 5 * float(age) - 161
    else:
        bmr = 10 * float(weight_kg) + 6.25 * float(height_cm) - 5 * float(age) + 5
    bmr = max(bmr, 0.0)
    return {
        'bmr': _round_inr(bmr),
        'primary': _round_inr(bmr),
    }


def calorie_calculator(
    weight_kg: float,
    height_cm: float,
    age: float,
    gender: str = 'male',
    activity: str = 'moderate',
    **_kwargs,
) -> Dict[str, Any]:
    bmr = bmr_calculator(weight_kg, height_cm, age, gender)['bmr']
    factors = {'sedentary': 1.2, 'light': 1.375, 'moderate': 1.55, 'active': 1.725, 'very_active': 1.9}
    tdee = bmr * factors.get(str(activity), 1.55)
    return {
        'calories': _round_inr(tdee),
        'bmr': bmr,
        'cut': _round_inr(tdee - 500),
        'bulk': _round_inr(tdee + 300),
        'primary': _round_inr(tdee),
    }


def body_fat_calculator(
    height_cm: float,
    waist_cm: float,
    neck_cm: float,
    gender: str = 'male',
    hip_cm: float = 90,
    **_kwargs,
) -> Dict[str, Any]:
    height = max(float(height_cm), 1.0)
    waist = max(float(waist_cm), 1.0)
    neck = max(float(neck_cm), 1.0)
    hip = max(float(hip_cm), 1.0)
    if gender == 'female':
        value = 495 / (1.29579 - 0.35004 * math.log10(max(waist + hip - neck, 0.1)) + 0.22100 * math.log10(height)) - 450
    else:
        value = 495 / (1.0324 - 0.19077 * math.log10(max(waist - neck, 0.1)) + 0.15456 * math.log10(height)) - 450
    value = min(max(value, 1.0), 70.0)
    return {
        'body_fat': round(value, 1),
        'primary': round(value, 1),
    }


def macro_calculator(calories: float, goal: str = 'maintain', **_kwargs) -> Dict[str, Any]:
    kcal = max(float(calories), 0.0)
    if goal == 'cut':
        p_pct, c_pct, f_pct = 0.40, 0.35, 0.25
    elif goal == 'bulk':
        p_pct, c_pct, f_pct = 0.30, 0.45, 0.25
    else:
        p_pct, c_pct, f_pct = 0.30, 0.40, 0.30
    protein = (kcal * p_pct) / 4.0
    carbs = (kcal * c_pct) / 4.0
    fat = (kcal * f_pct) / 9.0
    return {
        'protein': _round_inr(protein),
        'carbs': _round_inr(carbs),
        'fat': _round_inr(fat),
        'calories': _round_inr(kcal),
        'primary': _round_inr(protein),
    }


def ovulation_calculator(lmp: Any = None, cycle_length: float = 28, **_kwargs) -> Dict[str, Any]:
    start = _parse_date(lmp)
    cycle = int(round(float(cycle_length)))
    ovulation = start + timedelta(days=cycle - 14)
    fertile_start = ovulation - timedelta(days=5)
    next_period = start + timedelta(days=cycle)
    return {
        'ovulation_date': _fmt_date(ovulation),
        'fertile_start': _fmt_date(fertile_start),
        'fertile_end': _fmt_date(ovulation),
        'next_period': _fmt_date(next_period),
        'primary': _fmt_date(ovulation),
    }


def pregnancy_calculator(lmp: Any = None, **_kwargs) -> Dict[str, Any]:
    start = _parse_date(lmp)
    today = date.today()
    days = max((today - start).days, 0)
    weeks = days // 7
    trimester = 1 if weeks < 13 else 2 if weeks < 27 else 3
    due = start + timedelta(days=280)
    return {
        'weeks': weeks,
        'days': days % 7,
        'trimester': trimester,
        'due_date': _fmt_date(due),
        'primary': weeks,
    }


def pregnancy_conception(lmp: Any = None, cycle_length: float = 28, **_kwargs) -> Dict[str, Any]:
    start = _parse_date(lmp)
    cycle = int(round(float(cycle_length)))
    conception = start + timedelta(days=cycle - 14)
    return {
        'conception_date': _fmt_date(conception),
        'due_date': _fmt_date(start + timedelta(days=280)),
        'primary': _fmt_date(conception),
    }


def pregnancy_weight_gain(pre_weight: float, height_cm: float, week: float, **_kwargs) -> Dict[str, Any]:
    h = max(float(height_cm), 1.0) / 100.0
    bmi = float(pre_weight) / (h * h)
    if bmi < 18.5:
        total = 14.0
    elif bmi < 25:
        total = 12.5
    elif bmi < 30:
        total = 9.0
    else:
        total = 7.0
    w = min(max(float(week), 0.0), 40.0)
    recommended = total * (w / 40.0)
    return {
        'recommended_gain': round(recommended, 1),
        'total_gain': round(total, 1),
        'bmi': round(bmi, 1),
        'primary': round(recommended, 1),
    }


def due_date_calculator(lmp: Any = None, **_kwargs) -> Dict[str, Any]:
    start = _parse_date(lmp)
    due = start + timedelta(days=280)
    return {
        'due_date': _fmt_date(due),
        'conception_date': _fmt_date(start + timedelta(days=14)),
        'primary': _fmt_date(due),
    }


def gst(amount: float, gst_rate: float, mode: str = 'exclusive', **_kwargs) -> Dict[str, Any]:
    amt = float(amount)
    rate = float(gst_rate) / 100.0
    if mode == 'inclusive':
        total = amt
        base = amt / (1 + rate) if rate > -0.999 else amt
        gst_amt = total - base
    else:
        base = amt
        gst_amt = amt * rate
        total = base + gst_amt
    return {
        'gst_amount': _round_inr(gst_amt),
        'base_amount': _round_inr(base),
        'total': _round_inr(total),
        'primary': _round_inr(gst_amt),
    }


_SEO_ENGINES: Dict[str, Callable[..., Dict[str, Any]]] = {
    'sip-calculator': sip,
    'goal-sip-calculator': goal_sip,
    'step-up-sip-calculator': step_up_sip,
    'lumpsum-calculator': lumpsum,
    'investment-calculator': lumpsum,
    'emi-calculator': emi,
    'home-loan-emi-calculator': emi,
    'car-loan-emi-calculator': emi,
    'personal-loan-emi-calculator': emi,
    'compound-interest-calculator': compound_interest,
    'inflation-calculator': inflation,
    'fd-calculator': fd,
    'ppf-calculator': ppf,
    'ssy-calculator': ssy,
    'savings-calculator': savings_calculator,
    'human-life-value-calculator': human_life_value,
    'health-insurance-calculator': health_insurance,
    'life-insurance-calculator': life_insurance,
    'term-insurance-calculator': term_insurance,
    'lic-calculator': lic_calculator,
    'ulip-calculator': ulip_calculator,
    'home-loan-insurance-calculator': home_loan_insurance,
    'car-insurance-calculator': car_insurance,
    'bike-insurance-calculator': bike_insurance,
    'idv-calculator': idv_calculator,
    'travel-insurance-calculator': travel_insurance,
    'swp-calculator': swp,
    'nps-calculator': nps,
    'retirement-calculator': retirement,
    'pension-calculator': pension,
    'epf-calculator': epf,
    'rd-calculator': rd,
    'elss-calculator': sip,
    'gratuity-calculator': gratuity,
    'cost-of-delay-calculator': cost_of_delay,
    'power-of-compounding-calculator': power_of_compounding,
    'future-value-calculator': future_value,
    'increasing-contribution-calculator': increasing_contribution,
    'bond-yield-calculator': bond_yield,
    'annuity-payout-calculator': annuity_payout,
    'net-worth-calculator': net_worth,
    'asset-allocation-calculator': asset_allocation,
    'present-value-calculator': present_value,
    'income-tax-calculator': income_tax,
    'hra-calculator': hra,
    'gst-calculator': gst,
    'section-80d-calculator': section_80d,
    'ulip-vs-mutual-fund-calculator': ulip_vs_mutual_fund,
    'endowment-vs-mutual-fund-calculator': endowment_vs_mutual_fund,
    'family-floater-vs-individual-calculator': family_floater_vs_individual,
    'super-top-up-calculator': super_top_up,
    'life-cover-calculator': life_cover_calculator,
    'critical-illness-cover-calculator': critical_illness_cover,
    'sip-vs-lumpsum-calculator': sip_vs_lumpsum,
    'bmi-calculator': bmi_calculator,
    'ideal-weight-calculator': ideal_weight_calculator,
    'bmr-calculator': bmr_calculator,
    'calorie-calculator': calorie_calculator,
    'body-fat-calculator': body_fat_calculator,
    'macro-calculator': macro_calculator,
    'ovulation-calculator': ovulation_calculator,
    'pregnancy-calculator': pregnancy_calculator,
    'pregnancy-conception-calculator': pregnancy_conception,
    'pregnancy-weight-gain-calculator': pregnancy_weight_gain,
    'due-date-calculator': due_date_calculator,
}

_LEGACY_ALIASES = {
    'sip': 'sip-calculator',
    'goal-sip': 'goal-sip-calculator',
    'step-up-sip': 'step-up-sip-calculator',
    'lumpsum': 'lumpsum-calculator',
    'emi': 'emi-calculator',
    'compound-interest': 'compound-interest-calculator',
    'inflation': 'inflation-calculator',
    'fd': 'fd-calculator',
    'ppf': 'ppf-calculator',
    'human-life-value': 'human-life-value-calculator',
    'insurance-premium': 'health-insurance-calculator',
    'swp': 'swp-calculator',
    'nps': 'nps-calculator',
    'retirement': 'retirement-calculator',
    'pension': 'pension-calculator',
    'epf': 'epf-calculator',
    'rd': 'rd-calculator',
    'gratuity': 'gratuity-calculator',
    'cost-of-delay': 'cost-of-delay-calculator',
    'power-of-compounding': 'power-of-compounding-calculator',
    'future-value': 'future-value-calculator',
    'increasing-contribution': 'increasing-contribution-calculator',
    'bond-yield': 'bond-yield-calculator',
    'annuity-payout': 'annuity-payout-calculator',
    'net-worth': 'net-worth-calculator',
    'asset-allocation': 'asset-allocation-calculator',
    'present-value': 'present-value-calculator',
    'income-tax': 'income-tax-calculator',
    'hra': 'hra-calculator',
    'gst': 'gst-calculator',
}

ENGINES: Dict[str, Callable[..., Dict[str, Any]]] = dict(_SEO_ENGINES)
for _old, _new in _LEGACY_ALIASES.items():
    ENGINES[_old] = _SEO_ENGINES[_new]


def calculate(slug: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
    fn = ENGINES.get(slug)
    if not fn:
        raise ValueError(f'No engine for calculator slug: {slug}')
    return fn(**inputs)
