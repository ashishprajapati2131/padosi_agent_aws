from django.shortcuts import render, redirect
from django.http import HttpResponse
from apps.admin_panel.services.spreadsheet_safety import safe_csv_writer
from datetime import datetime
from .dashboard import _get_admin_from_session
from ..selectors.events import fetch_event_list, fetch_event, fetch_event_registrants

def event_list(request):
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect('admin_login')

    events = fetch_event_list()

    context = {
        'admin': admin,
        'events': events,
    }
    return render(request, 'admin/events/list.html', context)


def event_show(request, event_id):
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect('admin_login')

    event = None
    registrants = []
    
    # KPI counters
    total_entries = 0
    step1_drop = 0
    step2_drop = 0
    fully_completed = 0

    event = fetch_event(event_id)
    if event is None:
        return redirect('admin_events_index')

    for reg in fetch_event_registrants(event_id):
        # Format insurance segments
        if reg['insurance_segments']:
            reg['insurance_segments'] = reg['insurance_segments'].split(',')
        else:
            reg['insurance_segments'] = []

        registrants.append(reg)

        # Update KPI counters
        total_entries += 1
        step = reg['current_step']
        if step == 1:
            step1_drop += 1
        elif step == 2:
            step2_drop += 1
        elif step == 3:
            fully_completed += 1

    context = {
        'admin': admin,
        'event': event,
        'registrants': registrants,
        'total_entries': total_entries,
        'step1_drop': step1_drop,
        'step2_drop': step2_drop,
        'fully_completed': fully_completed,
    }
    return render(request, 'admin/events/show.html', context)


def get_step_name(step):
    """Helper matching Laravel's getStepName() exactly."""
    if step == 1:
        return 'Form Filled - Dropped at Plan selection'
    elif step == 2:
        return 'Plan Selected - Dropped at Checkout'
    elif step == 3:
        return 'Completed - Registered & Paid'
    return 'Unknown'


def event_export(request, event_id):
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect('admin_login')

    event = fetch_event(event_id)
    if event is None:
        return redirect('admin_events_index')

    # Fetch registrants (exact same query as show)
    registrants = fetch_event_registrants(event_id)

    # Generate CSV response
    event_name_clean = str(event['name']).lower().replace(' ', '_')
    date_str = datetime.now().strftime('%Y-%m-%d')
    filename = f"event_{event_name_clean}_registrations_{date_str}.csv"

    response = HttpResponse(content_type='text/csv; charset=UTF-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['Pragma'] = 'no-cache'
    response['Cache-Control'] = 'must-revalidate, post-check=0, pre-check=0'
    response['Expires'] = '0'

    # Write UTF-8 BOM
    response.write(b'\xEF\xBB\xBF')

    writer = safe_csv_writer(response)
    
    # Exact Laravel headers
    writer.writerow([
        'Registration ID', 'Full Name', 'Email Address', 'Mobile Number', 
        'Insurance Segments', 'Pin Code', 'Promo Code', 'Current Step', 
        'Selected Plan', 'Registration Status', 'Payment Status', 
        'Razorpay Order ID', 'Razorpay Payment ID', 'Date Registered'
    ])

    for r in registrants:
        segments = r['insurance_segments'].replace(',', ', ') if r['insurance_segments'] else ''
        pincode = r['pincode'] if r['pincode'] else 'N/A'
        promo = r['promocode'] if r['promocode'] else 'N/A'
        
        step_val = r['current_step']
        step_str = f"{step_val}/3 ({get_step_name(step_val)})"
        
        plan = str(r['selected_plan']).capitalize() if r['selected_plan'] else 'None'
        reg_status = str(r['status']).capitalize() if r['status'] else ''
        pay_status = str(r['payment_status']).capitalize() if r['payment_status'] else 'Pending'
        
        razor_order = r['razorpay_order_id'] if r['razorpay_order_id'] else 'N/A'
        razor_pay = r['razorpay_payment_id'] if r['razorpay_payment_id'] else 'N/A'
        
        # Django created_at format
        date_reg = r['created_at'].strftime('%Y-%m-%d %H:%M:%S') if r['created_at'] else ''

        writer.writerow([
            r['id'],
            r['fullname'],
            r['email'],
            r['mobile'],
            segments,
            pincode,
            promo,
            step_str,
            plan,
            reg_status,
            pay_status,
            razor_order,
            razor_pay,
            date_reg
        ])

    return response

