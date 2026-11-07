import logging
from django.http import JsonResponse
from django.urls import reverse

from apps.admin_panel.selectors.search import (
    fetch_matching_agents,
    fetch_matching_invoices,
    fetch_matching_users,
)

logger = logging.getLogger(__name__)

def admin_search(request):
    """
    Global search for admin panel.
    Laravel equivalent: AdminSearchController@search
    """
    query = request.GET.get('q', '').strip()
    if not query or len(query) < 2:
        return JsonResponse({'results': []})

    results = []
    
    # Use LIKE for partial matches
    search_pattern = f"%{query}%"
    
    try:
        # 1. Search Agents
        for agent in fetch_matching_agents(search_pattern):
            results.append({
                'type': 'Agent',
                'title': agent['fullname'],
                'subtitle': f"{agent['email']} | {agent['mobile']}",
                'url': reverse('admin_agents_manage', kwargs={'id': agent['id']}),
                'icon': 'fa-user-tie',
                'color': '#1d7d5d'
            })

        # 2. Search Users
        for user in fetch_matching_users(search_pattern):
            results.append({
                'type': 'User',
                'title': user['fullname'],
                'subtitle': user['email'],
                'url': reverse('admin_users_edit', kwargs={'user_id': user['id']}),
                'icon': 'fa-user',
                'color': '#3b82f6'
            })

        # 3. Search Invoices
        for invoice in fetch_matching_invoices(search_pattern):
            results.append({
                'type': 'Invoice',
                'title': f"INV #{invoice['invoice_number']}",
                'subtitle': f"₹{invoice['amount']}",
                'url': reverse('admin_invoice_preview', kwargs={'invoice_id': invoice['id']}),
                'icon': 'fa-file-invoice',
                'color': '#8b5cf6'
            })
    except Exception as e:
        logger.error(f"Search error: {e}")

    return JsonResponse({'results': results})
