"""Calculator catalog write flows used by apps/admin_panel/views/calculators.py."""

from apps.home.models.calculator import flush_calculator_cache
from apps.home.models.calculator_category import CalculatorCategory


def save_calculator(calc):
    """Persist a calculator whose fields the view already set, then flush the public cache."""
    calc.save()
    flush_calculator_cache()


def toggle_calculator_status(calc):
    """Flip is_active. Returns False (and forces is_active off) when the engine is not shipped."""
    calc.is_active = not calc.is_active
    if calc.is_active and not calc.engine_ready:
        calc.is_active = False
        calc.save(update_fields=["is_active", "updated_at"])
        return False

    calc.save(update_fields=["is_active", "updated_at"])
    flush_calculator_cache()
    return True


def set_calculator_category(calc, category):
    calc.category = category
    calc.save(update_fields=["category", "updated_at"])
    flush_calculator_cache()


def update_category(
    cat, *, name, slug, icon_class, meta_title, meta_description, sort_order
):
    """Save category fields. Caller flushes the calculator cache."""
    cat.name = name
    cat.slug = slug
    cat.icon_class = icon_class
    cat.meta_title = meta_title
    cat.meta_description = meta_description
    cat.sort_order = sort_order
    cat.save()
    return cat


def create_category(
    *, name, slug, icon_class, meta_title, meta_description, sort_order
):
    """Create an active category. Caller flushes the calculator cache."""
    return CalculatorCategory.objects.create(
        name=name,
        slug=slug,
        icon_class=icon_class,
        meta_title=meta_title,
        meta_description=meta_description,
        sort_order=sort_order,
        is_active=True,
    )


def toggle_category(cat):
    cat.is_active = not cat.is_active
    cat.save(update_fields=["is_active", "updated_at"])
    flush_calculator_cache()


def delete_category(cat):
    """Delete the category and flush the cache; returns its slug."""
    slug = cat.slug
    cat.delete()
    flush_calculator_cache()
    return slug
