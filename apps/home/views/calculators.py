"""Public calculator hub and detail pages."""
import json

from django.http import Http404, HttpResponsePermanentRedirect
from django.shortcuts import render
from django.urls import reverse

from apps.home.models.calculator import Calculator
from apps.home.models.calculator_category import CalculatorCategory
from apps.home.calculators.registry import DEFAULT_DISCLAIMER, SLUG_REDIRECTS, engine_slug_for, get_spec


def _is_admin(request):
    return bool(request.session.get('admin_id'))


def _public_queryset():
    return (
        Calculator.objects.filter(is_active=True, engine_ready=True)
        .select_related('category')
        .order_by('sort_order', 'title')
    )


def _live_categories():
    return (
        CalculatorCategory.objects.filter(is_active=True)
        .order_by('sort_order', 'name')
    )


def build_hub_tabs(categories, calculators):
    by_cat = {}
    for calc in calculators:
        by_cat.setdefault(calc.category_id, []).append(calc)
    tabs = []
    for cat in categories:
        items = by_cat.get(cat.id)
        if not items:
            continue
        tabs.append({'category': cat, 'items': items, 'count': len(items)})
    return tabs


def _can_preview(request, calc):
    if calc.is_active and calc.engine_ready:
        return True
    if request.GET.get('preview') == '1' and _is_admin(request) and calc.engine_ready:
        return True
    return False


def _build_fields(calc, spec):
    rows = []
    overrides = calc.default_inputs or {}
    for field in spec.get('fields', []):
        row = dict(field)
        row['current'] = overrides.get(field['id'], field.get('default'))
        options = []
        for opt in field.get('options') or []:
            option = dict(opt)
            option['selected'] = str(opt.get('value')) == str(row['current'])
            options.append(option)
        row['options'] = options
        rows.append(row)
    return rows


def _render_hub(request, category=None):
    calculators = list(_public_queryset())
    tabs = build_hub_tabs(_live_categories(), calculators)
    active = category
    if active is None and tabs:
        active = tabs[0]['category']
    if active and not any(tab['category'].id == active.id for tab in tabs):
        if not category:
            active = tabs[0]['category'] if tabs else None
        else:
            raise Http404('Category not found')

    if category:
        meta_title = category.meta_title or f'{category.name} Calculators India | PadosiAgent'
        meta_description = category.meta_description or (
            f'Free {category.name.lower()} calculators. Educational estimates — talk to a licensed PadosiAgent.'
        )
        canonical = request.build_absolute_uri(
            reverse('home:calculator_detail', kwargs={'slug': category.slug})
        )
    else:
        meta_title = 'Financial Calculators India | SIP, EMI, Insurance | PadosiAgent'
        meta_description = (
            'Free SIP, EMI, FD, PPF, insurance and retirement calculators. '
            'Educational estimates — talk to a licensed PadosiAgent for advice.'
        )
        canonical = request.build_absolute_uri(reverse('home:calculators'))

    return render(request, 'public/calculators/index.html', {
        'tabs': tabs,
        'active_category': active,
        'calculators': calculators,
        'meta_title': meta_title,
        'meta_description': meta_description,
        'canonical_url': canonical,
        'is_category_page': bool(category),
    })


def hub(request):
    slug = request.GET.get('cat')
    if slug:
        category = CalculatorCategory.objects.filter(slug=slug, is_active=True).first()
        if category:
            return _render_hub(request, category)
    return _render_hub(request)


def detail_or_category(request, slug):
    target = SLUG_REDIRECTS.get(slug)
    if target:
        return HttpResponsePermanentRedirect(
            reverse('home:calculator_detail', kwargs={'slug': target})
        )

    category = CalculatorCategory.objects.filter(slug=slug).first()
    if category:
        if not category.is_active:
            raise Http404('Category not found')
        return _render_hub(request, category)

    return detail(request, slug)


def detail(request, slug):
    calc = Calculator.objects.select_related('category').filter(slug=slug).first()
    if not calc:
        raise Http404('Calculator not found')
    if not _can_preview(request, calc):
        raise Http404('Calculator not found')

    spec = get_spec(calc.slug)
    if not spec or not calc.engine_ready:
        raise Http404('Calculator not found')

    fields = _build_fields(calc, spec)
    faqs = calc.faq_json if isinstance(calc.faq_json, list) and calc.faq_json else (spec.get('faqs') or [])
    related = list(
        _public_queryset().exclude(id=calc.id).filter(category=calc.category)[:8]
    )

    config = {
        'slug': engine_slug_for(calc.slug),
        'fields': fields,
        'outputs': spec.get('outputs') or {},
    }

    faq_entities = [
        {
            '@type': 'Question',
            'name': item.get('q', ''),
            'acceptedAnswer': {'@type': 'Answer', 'text': item.get('a', '')},
        }
        for item in faqs if item.get('q') and item.get('a')
    ]
    json_ld = {
        '@context': 'https://schema.org',
        '@graph': [
            {
                '@type': 'WebApplication',
                'name': calc.title,
                'url': request.build_absolute_uri(
                    reverse('home:calculator_detail', kwargs={'slug': calc.slug})
                ),
                'applicationCategory': 'FinanceApplication',
                'offers': {'@type': 'Offer', 'price': '0', 'priceCurrency': 'INR'},
                'description': calc.meta_description or calc.short_description,
            },
        ],
    }
    if faq_entities:
        json_ld['@graph'].append({'@type': 'FAQPage', 'mainEntity': faq_entities})

    return render(request, 'public/calculators/detail.html', {
        'calc': calc,
        'spec': spec,
        'fields': fields,
        'faqs': faqs,
        'related': related,
        'config': config,
        'category_label': calc.category.name if calc.category_id else '',
        'disclaimer': calc.disclaimer or DEFAULT_DISCLAIMER,
        'is_preview': not calc.is_active,
        'canonical_url': request.build_absolute_uri(
            reverse('home:calculator_detail', kwargs={'slug': calc.slug})
        ),
        'json_ld': json.dumps(json_ld, ensure_ascii=True),
    })
