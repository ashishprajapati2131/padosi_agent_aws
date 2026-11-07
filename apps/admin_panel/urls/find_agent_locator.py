"""Admin routes served by views/find_agent_locator.py."""
from django.urls import path

from ..views.find_agent_locator import (
    locator_index as find_agent_locator_index,
    extract_coordinates as find_agent_locator_extract,
    save_pincode_to_master as find_agent_locator_save_pincode,
    search_agents as find_agent_locator_search_agents,
    assign_agent_to_pincode as find_agent_locator_assign_agent,
    create_and_add_agent as find_agent_locator_create_agent,
    live_preview as find_agent_locator_live_preview,
    unlink_agent_pincode as find_agent_locator_unlink_agent,
)

urlpatterns = [
    path("admin/find-agent-locator/",               find_agent_locator_index,          name="admin_find_agent_locator"),
    path("admin/find-agent-locator/extract/",       find_agent_locator_extract,        name="admin_find_agent_locator_extract"),
    path("admin/find-agent-locator/save-pincode/",  find_agent_locator_save_pincode,   name="admin_find_agent_locator_save_pincode"),
    path("admin/find-agent-locator/search-agents/", find_agent_locator_search_agents,  name="admin_find_agent_locator_search_agents"),
    path("admin/find-agent-locator/assign-agent/",  find_agent_locator_assign_agent,   name="admin_find_agent_locator_assign_agent"),
    path("admin/find-agent-locator/create-agent/",  find_agent_locator_create_agent,   name="admin_find_agent_locator_create_agent"),
    path("admin/find-agent-locator/live-preview/",  find_agent_locator_live_preview,   name="admin_find_agent_locator_live_preview"),
    path("admin/find-agent-locator/unlink-agent/",  find_agent_locator_unlink_agent,   name="admin_find_agent_locator_unlink_agent"),
]
