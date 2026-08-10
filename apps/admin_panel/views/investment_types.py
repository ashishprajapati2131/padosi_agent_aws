import logging
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_http_methods
from django.utils import timezone

from apps.admin_panel.views.dashboard import _get_admin_from_session
from apps.agents.models import InvestmentType

logger = logging.getLogger(__name__)

@require_http_methods(["GET"])
def index(request):
    """List all investment types."""
    if not _get_admin_from_session(request): return redirect('admin_login')
    investment_types = InvestmentType.objects.all().order_by('name')
    return render(request, 'admin/investment_types/index.html', {'investment_types': investment_types})

@require_POST
def store(request):
    """Create a new investment type."""
    if not _get_admin_from_session(request): return redirect('admin_login')
    name = request.POST.get('name', '').strip()
    is_active = request.POST.get('is_active') == '1'
    
    if not name:
        messages.error(request, 'Investment Type name is required.')
        return redirect('admin_investment_types_index')
        
    if InvestmentType.objects.filter(name__iexact=name).exists():
        messages.error(request, 'An Investment Type with this name already exists.')
        return redirect('admin_investment_types_index')
        
    try:
        InvestmentType.objects.create(name=name, is_active=is_active)
        messages.success(request, 'Investment Type created successfully.')
    except Exception as e:
        logger.error(f"Error creating investment type: {e}")
        messages.error(request, 'An error occurred while creating the investment type.')
        
    return redirect('admin_investment_types_index')

@require_POST
def update(request, pk):
    """Update an existing investment type."""
    if not _get_admin_from_session(request): return redirect('admin_login')
    name = request.POST.get('name', '').strip()
    is_active = request.POST.get('is_active') == '1'
    
    try:
        inv_type = InvestmentType.objects.get(pk=pk)
        
        if not name:
            messages.error(request, 'Investment Type name is required.')
            return redirect('admin_investment_types_index')
            
        if InvestmentType.objects.filter(name__iexact=name).exclude(pk=pk).exists():
            messages.error(request, 'An Investment Type with this name already exists.')
            return redirect('admin_investment_types_index')
            
        inv_type.name = name
        inv_type.is_active = is_active
        inv_type.save()
        messages.success(request, 'Investment Type updated successfully.')
    except InvestmentType.DoesNotExist:
        messages.error(request, 'Investment Type not found.')
    except Exception as e:
        logger.error(f"Error updating investment type: {e}")
        messages.error(request, 'An error occurred while updating the investment type.')
        
    return redirect('admin_investment_types_index')

@require_POST
def delete(request, pk):
    """Delete an investment type."""
    if not _get_admin_from_session(request): return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=401)
    try:
        inv_type = InvestmentType.objects.get(pk=pk)
        inv_type.delete()
        return JsonResponse({'success': True, 'message': 'Investment Type deleted successfully.'})
    except InvestmentType.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Investment Type not found.'}, status=404)
    except Exception as e:
        logger.error(f"Error deleting investment type: {e}")
        return JsonResponse({'success': False, 'message': 'An error occurred while deleting.'}, status=500)

@require_POST
def toggle_status(request, pk):
    """Toggle the active status of an investment type."""
    if not _get_admin_from_session(request): return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=401)
    try:
        inv_type = InvestmentType.objects.get(pk=pk)
        inv_type.is_active = not inv_type.is_active
        inv_type.save()
        
        status_text = 'activated' if inv_type.is_active else 'deactivated'
        return JsonResponse({'success': True, 'message': f'Investment Type {status_text} successfully.'})
    except InvestmentType.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Investment Type not found.'}, status=404)
    except Exception as e:
        logger.error(f"Error toggling investment type status: {e}")
        return JsonResponse({'success': False, 'message': 'An error occurred while updating status.'}, status=500)
