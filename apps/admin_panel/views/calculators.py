"""Admin calculator catalog — list, toggle, edit copy/SEO, category CRUD."""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.utils.text import slugify
from django.views.decorators.http import require_POST, require_http_methods

from apps.home.models.calculator import Calculator, flush_calculator_cache
from apps.home.models.calculator_category import CalculatorCategory
from apps.home.calculators.registry import get_spec
from apps.admin_panel.models.admin_activity_log import AdminActivityLog
from apps.admin_panel.views.dashboard import _get_admin_from_session


def _require_admin(request):
    return _get_admin_from_session(request)


def _categories():
    return CalculatorCategory.objects.all().order_by('sort_order', 'name')


@require_http_methods(['GET'])
def index(request):
    if not _require_admin(request):
        return redirect('admin_login')

    qs = Calculator.objects.select_related('category').all().order_by('sort_order', 'title')
    status = request.GET.get('status', 'all')
    category = request.GET.get('category', 'all')
    tab = request.GET.get('tab', 'calculators')
    if status == 'active':
        qs = qs.filter(is_active=True)
    elif status == 'hidden':
        qs = qs.filter(is_active=False)
    if category and category != 'all':
        qs = qs.filter(category__slug=category)

    all_rows = list(Calculator.objects.all())
    cats = list(_categories())
    return render(request, 'admin/content/calculators.html', {
        'calculators': qs,
        'categories': cats,
        'filter_status': status,
        'filter_category': category,
        'active_tab': tab if tab in ('calculators', 'categories') else 'calculators',
        'active_count': sum(1 for c in all_rows if c.is_active),
        'hidden_count': sum(1 for c in all_rows if not c.is_active),
        'ready_count': sum(1 for c in all_rows if c.engine_ready),
        'total_count': len(all_rows),
        'category_count': len(cats),
    })


@require_http_methods(['GET', 'POST'])
def edit(request, pk):
    if not _require_admin(request):
        return redirect('admin_login')

    calc = get_object_or_404(Calculator.objects.select_related('category'), pk=pk)
    spec = get_spec(calc.slug) or {'fields': [], 'faqs': []}
    cats = list(_categories())

    if request.method == 'POST':
        calc.title = request.POST.get('title', calc.title).strip() or calc.title
        calc.short_description = request.POST.get('short_description', '').strip()
        calc.icon_class = request.POST.get('icon_class', calc.icon_class).strip() or calc.icon_class
        try:
            cat_id = int(request.POST.get('category') or 0)
        except (TypeError, ValueError):
            cat_id = 0
        category_obj = next((c for c in cats if c.id == cat_id), None)
        if category_obj:
            calc.category = category_obj
        try:
            calc.sort_order = int(request.POST.get('sort_order', calc.sort_order) or 0)
        except (TypeError, ValueError):
            pass
        calc.meta_title = request.POST.get('meta_title', '').strip()
        calc.meta_description = request.POST.get('meta_description', '').strip()
        calc.disclaimer = request.POST.get('disclaimer', '').strip()
        calc.cta_text = request.POST.get('cta_text', calc.cta_text).strip() or calc.cta_text
        calc.cta_url = request.POST.get('cta_url', calc.cta_url).strip() or calc.cta_url

        overrides = {}
        for field in spec.get('fields', []):
            raw = request.POST.get(f'default_{field["id"]}')
            if raw is None or raw == '':
                continue
            if field.get('type') in ('range', 'number'):
                try:
                    num = float(raw)
                    overrides[field['id']] = int(num) if num == int(num) else num
                except (TypeError, ValueError):
                    continue
            else:
                overrides[field['id']] = raw
        calc.default_inputs = overrides

        faqs = []
        questions = request.POST.getlist('faq_q[]')
        answers = request.POST.getlist('faq_a[]')
        for q, a in zip(questions, answers):
            q, a = q.strip(), a.strip()
            if q and a:
                faqs.append({'q': q, 'a': a})
        calc.faq_json = faqs
        calc.save()
        flush_calculator_cache()
        AdminActivityLog.log(f'Updated calculator {calc.slug}', 'Calculator', model_id=calc.id, request=request)
        messages.success(request, 'Calculator updated successfully.')
        return redirect('admin_content_calculators_edit', pk=calc.id)

    field_rows = []
    for field in spec.get('fields', []):
        row = dict(field)
        current = (calc.default_inputs or {}).get(field['id'], field.get('default'))
        row['current'] = current
        options = []
        for opt in field.get('options') or []:
            option = dict(opt)
            option['selected'] = str(opt.get('value')) == str(current)
            options.append(option)
        row['options'] = options
        field_rows.append(row)

    faqs = calc.faq_json if isinstance(calc.faq_json, list) and calc.faq_json else (spec.get('faqs') or [])
    return render(request, 'admin/content/calculator_edit.html', {
        'calc': calc,
        'spec': spec,
        'field_rows': field_rows,
        'categories': cats,
        'faqs': faqs,
    })


@require_POST
def toggle_status(request, pk):
    if not _require_admin(request):
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=401)

    calc = get_object_or_404(Calculator, pk=pk)
    if not calc.engine_ready and not calc.is_active:
        return JsonResponse({
            'success': False,
            'message': 'Engine not shipped yet. This calculator cannot be activated.',
            'is_active': False,
        }, status=400)

    calc.is_active = not calc.is_active
    if calc.is_active and not calc.engine_ready:
        calc.is_active = False
        calc.save(update_fields=['is_active', 'updated_at'])
        return JsonResponse({
            'success': False,
            'message': 'Engine not shipped yet. This calculator cannot be activated.',
            'is_active': False,
        }, status=400)

    calc.save(update_fields=['is_active', 'updated_at'])
    flush_calculator_cache()
    status_text = 'activated' if calc.is_active else 'deactivated'
    AdminActivityLog.log(
        f'Toggled calculator {calc.slug} → {status_text}',
        'Calculator',
        model_id=calc.id,
        request=request,
    )
    return JsonResponse({
        'success': True,
        'is_active': calc.is_active,
        'message': f'Calculator {status_text} successfully.',
    })


@require_POST
def change_category(request, pk):
    if not _require_admin(request):
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=401)
    calc = get_object_or_404(Calculator, pk=pk)
    try:
        cat_id = int(request.POST.get('category_id') or 0)
    except (TypeError, ValueError):
        return JsonResponse({'success': False, 'message': 'Invalid category.'}, status=400)
    category = CalculatorCategory.objects.filter(pk=cat_id).first()
    if not category:
        return JsonResponse({'success': False, 'message': 'Category not found.'}, status=404)
    calc.category = category
    calc.save(update_fields=['category', 'updated_at'])
    flush_calculator_cache()
    AdminActivityLog.log(
        f'Moved calculator {calc.slug} to {category.slug}',
        'Calculator',
        model_id=calc.id,
        request=request,
    )
    return JsonResponse({'success': True, 'category': category.name})


@require_POST
def category_save(request):
    if not _require_admin(request):
        return redirect('admin_login')

    pk = request.POST.get('id')
    name = (request.POST.get('name') or '').strip()
    slug = slugify(request.POST.get('slug') or name)
    icon_class = (request.POST.get('icon_class') or 'fa-solid fa-folder').strip()
    meta_title = (request.POST.get('meta_title') or '').strip()
    meta_description = (request.POST.get('meta_description') or '').strip()
    try:
        sort_order = int(request.POST.get('sort_order') or 0)
    except (TypeError, ValueError):
        sort_order = 0

    if not name or not slug:
        messages.error(request, 'Name and slug are required.')
        return redirect('/admin/content/calculators/?tab=categories')

    if pk:
        cat = get_object_or_404(CalculatorCategory, pk=pk)
        if CalculatorCategory.objects.exclude(pk=cat.pk).filter(slug=slug).exists():
            messages.error(request, 'That slug is already used by another category.')
            return redirect('/admin/content/calculators/?tab=categories')
        cat.name = name
        cat.slug = slug
        cat.icon_class = icon_class
        cat.meta_title = meta_title
        cat.meta_description = meta_description
        cat.sort_order = sort_order
        cat.save()
        AdminActivityLog.log(f'Updated calculator category {cat.slug}', 'CalculatorCategory', model_id=cat.id, request=request)
        messages.success(request, 'Category updated.')
    else:
        if CalculatorCategory.objects.filter(slug=slug).exists():
            messages.error(request, 'That slug is already used by another category.')
            return redirect('/admin/content/calculators/?tab=categories')
        cat = CalculatorCategory.objects.create(
            name=name,
            slug=slug,
            icon_class=icon_class,
            meta_title=meta_title,
            meta_description=meta_description,
            sort_order=sort_order,
            is_active=True,
        )
        AdminActivityLog.log(f'Created calculator category {cat.slug}', 'CalculatorCategory', model_id=cat.id, request=request)
        messages.success(request, 'Category added.')
    flush_calculator_cache()
    return redirect('/admin/content/calculators/?tab=categories')


@require_POST
def category_toggle(request, pk):
    if not _require_admin(request):
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=401)
    cat = get_object_or_404(CalculatorCategory, pk=pk)
    cat.is_active = not cat.is_active
    cat.save(update_fields=['is_active', 'updated_at'])
    flush_calculator_cache()
    AdminActivityLog.log(
        f'Toggled calculator category {cat.slug} → {"on" if cat.is_active else "off"}',
        'CalculatorCategory',
        model_id=cat.id,
        request=request,
    )
    return JsonResponse({'success': True, 'is_active': cat.is_active})


@require_POST
def category_delete(request, pk):
    if not _require_admin(request):
        return redirect('admin_login')
    cat = get_object_or_404(CalculatorCategory, pk=pk)
    count = cat.calculators.count()
    if count:
        messages.error(request, f'Cannot delete “{cat.name}”: {count} calculator(s) still use it. Reassign them first.')
        return redirect('/admin/content/calculators/?tab=categories')
    slug = cat.slug
    cat.delete()
    flush_calculator_cache()
    AdminActivityLog.log(f'Deleted calculator category {slug}', 'CalculatorCategory', request=request)
    messages.success(request, 'Category removed.')
    return redirect('/admin/content/calculators/?tab=categories')
