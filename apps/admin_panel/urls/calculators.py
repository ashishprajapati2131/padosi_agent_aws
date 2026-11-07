"""Admin routes served by views/calculators.py."""
from django.urls import path

from ..views.calculators import (
    index as content_calculators_index,
    edit as content_calculators_edit,
    toggle_status as content_calculators_toggle,
    change_category as content_calculators_change_category,
    category_save as content_calculator_category_save,
    category_toggle as content_calculator_category_toggle,
    category_delete as content_calculator_category_delete,
)

urlpatterns = [
    path('admin/content/calculators/',                   content_calculators_index,   name='admin_content_calculators'),
    path('admin/content/calculators/<int:pk>/edit/',     content_calculators_edit,    name='admin_content_calculators_edit'),
    path('admin/content/calculators/<int:pk>/toggle/',   content_calculators_toggle,  name='admin_content_calculators_toggle'),
    path('admin/content/calculators/<int:pk>/category/', content_calculators_change_category, name='admin_content_calculators_category'),
    path('admin/content/calculators/categories/save/',   content_calculator_category_save, name='admin_content_calculator_categories_save'),
    path('admin/content/calculators/categories/<int:pk>/toggle/', content_calculator_category_toggle, name='admin_content_calculator_categories_toggle'),
    path('admin/content/calculators/categories/<int:pk>/delete/', content_calculator_category_delete, name='admin_content_calculator_categories_delete'),
]
