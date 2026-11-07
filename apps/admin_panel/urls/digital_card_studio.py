"""Admin routes served by views/digital_card_studio.py."""
from django.urls import path

from ..views.digital_card_studio import (
    digital_card_studio_index,
    update_studio_config,
    toggle_agent_card_visibility,
    admin_agent_card_detail_api,
    admin_agent_card_save_api,
)

urlpatterns = [
    path('admin/content/visiting-card-studio/', digital_card_studio_index, name='admin_digital_card_studio'),
    path('admin/visiting-card-studio/',         digital_card_studio_index, name='admin_digital_card_studio_direct'),
    path('admin/content/visiting-card-studio/update/', update_studio_config, name='admin_digital_card_studio_update'),
    path('admin/content/visiting-card-studio/agent/<int:agent_id>/toggle/', toggle_agent_card_visibility, name='admin_digital_card_agent_toggle'),
    path('admin/content/visiting-card-studio/agent/<int:agent_id>/detail/', admin_agent_card_detail_api, name='admin_digital_card_agent_detail'),
    path('admin/content/visiting-card-studio/agent/<int:agent_id>/save/', admin_agent_card_save_api, name='admin_digital_card_agent_save'),
]
