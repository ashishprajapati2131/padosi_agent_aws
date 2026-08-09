import json
import logging
from django.db import connection
from django.http import JsonResponse
from django.urls import reverse

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
        with connection.cursor() as cursor:
            # 1. Search Agents
            cursor.execute(
                """
                SELECT id, fullname, email, mobile 
                FROM agents 
                WHERE fullname LIKE %s OR email LIKE %s OR mobile LIKE %s
                LIMIT 5
                """, 
                [search_pattern, search_pattern, search_pattern]
            )
            for row in cursor.fetchall():
                agent_id, fullname, email, mobile = row
                results.append({
                    'type': 'Agent',
                    'title': fullname,
                    'subtitle': f"{email} | {mobile}",
                    'url': reverse('admin_agents_manage', kwargs={'id': agent_id}),
                    'icon': 'fa-user-tie',
                    'color': '#1d7d5d'
                })

            # 2. Search Users
            cursor.execute(
                """
                SELECT id, fullname, email, mobile 
                FROM users 
                WHERE fullname LIKE %s OR email LIKE %s OR mobile LIKE %s
                LIMIT 3
                """, 
                [search_pattern, search_pattern, search_pattern]
            )
            for row in cursor.fetchall():
                user_id, fullname, email, mobile = row
                results.append({
                    'type': 'User',
                    'title': fullname,
                    'subtitle': email,
                    'url': reverse('admin_users_edit', kwargs={'user_id': user_id}),
                    'icon': 'fa-user',
                    'color': '#3b82f6'
                })

            # 3. Search Invoices
            cursor.execute(
                """
                SELECT id, invoice_number, amount 
                FROM invoices 
                WHERE invoice_number LIKE %s
                LIMIT 3
                """, 
                [search_pattern]
            )
            for row in cursor.fetchall():
                inv_id, inv_num, amount = row
                results.append({
                    'type': 'Invoice',
                    'title': f"INV #{inv_num}",
                    'subtitle': f"₹{amount}",
                    'url': reverse('admin_invoice_preview', kwargs={'invoice_id': inv_id}),
                    'icon': 'fa-file-invoice',
                    'color': '#8b5cf6'
                })
    except Exception as e:
        logger.error(f"Search error: {e}")

    return JsonResponse({'results': results})
