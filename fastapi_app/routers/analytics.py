from fastapi import APIRouter, Depends, Query, HTTPException, status
from datetime import date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from typing import Optional, Dict, Any, List

from fastapi_app.database import get_db
from fastapi_app.dependencies.auth import get_current_agent
from fastapi_app.models.agent import Agent
from fastapi_app.models.agent_profile_view import AgentProfileView

router = APIRouter(
    prefix="/api/v1/agents/analytics",
    tags=["Analytics"]
)

@router.get("")
def get_analytics(
    period: int = Query(30, description="Period in days: 7, 30, or 90"),
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """
    Get profile discovery, views, impressions, CTR, and chart breakdown.
    """
    if period not in (7, 30, 90):
        period = 30

    today = date.today()
    period_start = today - timedelta(days=period - 1)
    prev_start = period_start - timedelta(days=period)
    prev_end = period_start - timedelta(days=1)

    agent_pincode = getattr(current_agent, 'agent_pincode', None) or ''

    # 1. Current period impressions
    impressions_curr = 0
    try:
        imp_row = db.execute(
            text("""
                SELECT SUM(impression_count) FROM agent_card_impressions
                WHERE agent_id = :agent_id AND impression_date >= :p_start AND impression_date <= :today
            """),
            {"agent_id": current_agent.id, "p_start": period_start, "today": today}
        ).fetchone()
        impressions_curr = int(imp_row[0] or 0) if imp_row else 0
    except Exception:
        pass

    # 2. Current period profile views
    views_curr = 0
    try:
        view_row = db.query(func.sum(AgentProfileView.view_count)).filter(
            AgentProfileView.agent_id == current_agent.id,
            AgentProfileView.view_date >= period_start,
            AgentProfileView.view_date <= today
        ).scalar()
        views_curr = int(view_row or 0)
    except Exception:
        pass

    # 3. Current period search events
    searches_curr = 0
    if agent_pincode:
        try:
            search_row = db.execute(
                text("""
                    SELECT SUM(event_count) FROM agent_search_events
                    WHERE pincode = :pincode AND search_date >= :p_start AND search_date <= :today
                """),
                {"pincode": agent_pincode, "p_start": period_start, "today": today}
            ).fetchone()
            searches_curr = int(search_row[0] or 0) if search_row else 0
        except Exception:
            pass

    # 4. Previous period impressions & views for % change
    impressions_prev = 0
    try:
        imp_prev_row = db.execute(
            text("""
                SELECT SUM(impression_count) FROM agent_card_impressions
                WHERE agent_id = :agent_id AND impression_date >= :prev_start AND impression_date <= :prev_end
            """),
            {"agent_id": current_agent.id, "prev_start": prev_start, "prev_end": prev_end}
        ).fetchone()
        impressions_prev = int(imp_prev_row[0] or 0) if imp_prev_row else 0
    except Exception:
        pass

    views_prev = 0
    try:
        view_prev_row = db.query(func.sum(AgentProfileView.view_count)).filter(
            AgentProfileView.agent_id == current_agent.id,
            AgentProfileView.view_date >= prev_start,
            AgentProfileView.view_date <= prev_end
        ).scalar()
        views_prev = int(view_prev_row or 0)
    except Exception:
        pass

    ctr_curr = round((views_curr / impressions_curr * 100), 1) if impressions_curr > 0 else 0.0
    ctr_prev = round((views_prev / impressions_prev * 100), 1) if impressions_prev > 0 else 0.0

    def pct_change(curr, prev):
        if prev == 0:
            return None
        return round(((curr - prev) / prev) * 100, 1)

    # 5. Daily timeseries data
    chart_labels = []
    chart_impressions = []
    chart_views = []
    chart_searches = []

    imp_by_date = {}
    try:
        imp_rows = db.execute(
            text("""
                SELECT impression_date, SUM(impression_count) FROM agent_card_impressions
                WHERE agent_id = :agent_id AND impression_date >= :p_start AND impression_date <= :today
                GROUP BY impression_date
            """),
            {"agent_id": current_agent.id, "p_start": period_start, "today": today}
        ).fetchall()
        imp_by_date = {r[0]: int(r[1] or 0) for r in imp_rows if r[0]}
    except Exception:
        pass

    views_by_date = {}
    try:
        v_rows = db.query(
            AgentProfileView.view_date,
            func.sum(AgentProfileView.view_count)
        ).filter(
            AgentProfileView.agent_id == current_agent.id,
            AgentProfileView.view_date >= period_start,
            AgentProfileView.view_date <= today
        ).group_by(AgentProfileView.view_date).all()
        views_by_date = {r[0]: int(r[1] or 0) for r in v_rows if r[0]}
    except Exception:
        pass

    searches_by_date = {}
    if agent_pincode:
        try:
            s_rows = db.execute(
                text("""
                    SELECT search_date, SUM(event_count) FROM agent_search_events
                    WHERE pincode = :pincode AND search_date >= :p_start AND search_date <= :today
                    GROUP BY search_date
                """),
                {"pincode": agent_pincode, "p_start": period_start, "today": today}
            ).fetchall()
            searches_by_date = {r[0]: int(r[1] or 0) for r in s_rows if r[0]}
        except Exception:
            pass

    for i in range(period):
        day = period_start + timedelta(days=i)
        chart_labels.append(day.strftime('%d %b'))
        chart_impressions.append(imp_by_date.get(day, 0))
        chart_views.append(views_by_date.get(day, 0))
        chart_searches.append(searches_by_date.get(day, 0))

    if impressions_curr == 0:
        insight = "Start getting discovered! Your profile analytics will appear here as people search for agents in your area."
    elif ctr_curr < 5:
        insight = f"Your click-through rate is {ctr_curr}%. Consider updating your profile photo and headline to attract more clicks."
    elif ctr_curr < 12:
        insight = f"Your click-through rate is {ctr_curr}% — close to average. A better photo or more reviews can push it higher."
    elif ctr_curr < 20:
        insight = f"Great engagement! Your click-through rate is {ctr_curr}%, which is above average."
    else:
        insight = f"Excellent! Your click-through rate is {ctr_curr}%. You are one of the most engaging profiles in your area."

    return {
        "success": True,
        "period": period,
        "summary": {
            "card_impressions": impressions_curr,
            "card_impressions_prev": impressions_prev,
            "card_impressions_change": pct_change(impressions_curr, impressions_prev),
            "profile_views": views_curr,
            "profile_views_prev": views_prev,
            "profile_views_change": pct_change(views_curr, views_prev),
            "ctr": ctr_curr,
            "ctr_prev": ctr_prev,
            "pincode_searches": searches_curr,
        },
        "chart": {
            "labels": chart_labels,
            "impressions": chart_impressions,
            "profile_views": chart_views,
            "searches": chart_searches
        },
        "insight": insight
    }
