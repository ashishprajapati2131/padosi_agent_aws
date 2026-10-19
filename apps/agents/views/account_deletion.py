from django.shortcuts import render
from django.views.decorators.http import require_GET


@require_GET
def account_deletion_view(request):
    """
    Renders the public account deletion & data privacy portal.
    Allows agents and users to view what data will be deleted vs retained,
    and initiate verified account deletion requests.
    """
    return render(request, 'public/delete_account.html', {
        'default_meta_title': 'Account Deletion & Data Privacy — PadosiAgent',
        'default_meta_description': 'Submit verified account deletion requests in compliance with DPDP regulations.',
    })
