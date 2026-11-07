from django.shortcuts import render, redirect
from django.db import connection
from .dashboard import _get_admin_from_session
from ..selectors.revenue import (
    fetch_active_agent_counts,
    fetch_month_revenue,
    fetch_monthly_revenue,
    fetch_plan_revenue_totals,
    fetch_raw_mrr,
    fetch_recent_subscriptions,
)

import datetime
import json

def revenue_dashboard(request):
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect('admin_login')

    with connection.cursor() as cursor:
        # 1. Monthly Revenue by plan (last 12 months)
        monthly_revenue = fetch_monthly_revenue(cursor, datetime.datetime.now())

        # 2. Active agent counts
        prof_count, starter_count, trial_count = fetch_active_agent_counts(cursor)
        total_subs = prof_count + starter_count + trial_count

        # 3. Revenue collected per plan (all-time, completed payments)
        pro_revenue, starter_revenue, trial_revenue, total_revenue = fetch_plan_revenue_totals(cursor)

        # 4. MRR
        now_ist = datetime.datetime.now()
        pro_mrr_raw, starter_mrr_raw = fetch_raw_mrr(cursor, now_ist)

        mrr = int(round(float(pro_mrr_raw) + float(starter_mrr_raw)))
        arr = mrr * 12

        # 5. Revenue this month vs last month
        now = datetime.datetime.now()
        revenue_this_month = fetch_month_revenue(cursor, now.month, now.year)

        last_month = now.replace(day=1) - datetime.timedelta(days=1)
        revenue_last_month = fetch_month_revenue(cursor, last_month.month, last_month.year)

        if revenue_last_month > 0:
            revenue_growth = round(((revenue_this_month - revenue_last_month) / revenue_last_month) * 100, 1)
        else:
            revenue_growth = 100 if revenue_this_month > 0 else 0

        # 6. Recent subscriptions
        recent_subs = fetch_recent_subscriptions(cursor)

    # To pass Chart data to JS easily
    labels = []
    prof_data = []
    starter_data = []
    trial_data = []
    for item in monthly_revenue:
        labels.append(item['label'])
        prof_data.append(float(item['professional'] or 0))
        starter_data.append(float(item['starter'] or 0))
        trial_data.append(float(item['trial'] or 0))

    pro_bar = round((float(pro_revenue) / total_revenue) * 100) if total_revenue > 0 else 0
    starter_bar = round((float(starter_revenue) / total_revenue) * 100) if total_revenue > 0 else 0
    trial_bar = round((float(trial_revenue) / total_revenue) * 100) if total_revenue > 0 else 0

    context = {
        'admin': admin,
        'profCount': prof_count,
        'starterCount': starter_count,
        'trialCount': trial_count,
        'totalSubs': total_subs,
        'mrr': mrr,
        'arr': arr,
        'revenueThisMonth': revenue_this_month,
        'revenueLastMonth': revenue_last_month,
        'revenueGrowth': revenue_growth,
        'totalRevenue': total_revenue,
        'proRevenue': float(pro_revenue),
        'starterRevenue': float(starter_revenue),
        'trialRevenue': float(trial_revenue),
        'proBar': pro_bar,
        'starterBar': starter_bar,
        'trialBar': trial_bar,
        'recentSubs': recent_subs,
        'chart_labels': json.dumps(labels),
        'chart_prof': json.dumps(prof_data),
        'chart_starter': json.dumps(starter_data),
        'chart_trial': json.dumps(trial_data),
    }

    return render(request, 'admin/revenue/dashboard.html', context)
