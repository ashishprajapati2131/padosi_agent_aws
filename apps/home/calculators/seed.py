from apps.home.calculators.registry import CALCULATORS, DEFAULT_CATEGORIES, SLUG_REDIRECTS


def seed_categories(CalculatorCategory):
    created = 0
    for spec in DEFAULT_CATEGORIES:
        defaults = {
            'name': spec['name'],
            'icon_class': spec['icon_class'],
            'is_active': spec.get('is_active', True),
            'sort_order': spec['sort_order'],
            'meta_title': spec.get('meta_title', ''),
            'meta_description': spec.get('meta_description', ''),
        }
        _, was_created = CalculatorCategory.objects.get_or_create(
            slug=spec['slug'],
            defaults=defaults,
        )
        if was_created:
            created += 1
    return created


def _rename_legacy_slugs(Calculator):
    renamed = set()
    for old, new in SLUG_REDIRECTS.items():
        if Calculator.objects.filter(slug=old).exists() and not Calculator.objects.filter(slug=new).exists():
            Calculator.objects.filter(slug=old).update(slug=new)
            renamed.add(new)
    return renamed


def seed_calculators(Calculator, CalculatorCategory=None, activate_all=False):
    """Idempotent seed. New slugs are inserted; existing rows refresh engine_ready.

    When an engine first becomes ready, the calculator is auto-activated.
    Admin copy, SEO, FAQs and later is_active toggles are left untouched after that,
    unless activate_all=True (used after a DB restore that wiped the catalog).
    """
    if CalculatorCategory is None:
        from apps.home.models.calculator_category import CalculatorCategory

    seed_categories(CalculatorCategory)
    renamed_slugs = _rename_legacy_slugs(Calculator)
    cats = {c.slug: c for c in CalculatorCategory.objects.all()}

    created = 0
    updated = 0
    for spec in CALCULATORS:
        category = cats.get(spec['category'])
        if category is None:
            continue
        defaults = {
            'title': spec['title'],
            'short_description': spec['short_description'],
            'category': category,
            'icon_class': spec['icon_class'],
            'engine_ready': spec['engine_ready'],
            'is_active': bool(spec['engine_ready']),
            'sort_order': spec['sort_order'],
            'meta_title': spec['meta_title'],
            'meta_description': spec['meta_description'],
            'disclaimer': spec['disclaimer'],
            'cta_text': spec['cta_text'],
            'cta_url': spec['cta_url'],
            'default_inputs': {},
            'faq_json': spec.get('faqs') or [],
        }
        obj, was_created = Calculator.objects.get_or_create(
            slug=spec['slug'],
            defaults=defaults,
        )
        if was_created:
            created += 1
            continue
        fields = []
        becoming_ready = spec['engine_ready'] and not obj.engine_ready
        if spec['slug'] in renamed_slugs:
            obj.title = spec['title']
            obj.short_description = spec['short_description']
            obj.meta_title = spec['meta_title']
            obj.meta_description = spec['meta_description']
            obj.icon_class = spec['icon_class']
            obj.sort_order = spec['sort_order']
            obj.category = category
            fields.extend(['title', 'short_description', 'meta_title', 'meta_description', 'icon_class', 'sort_order', 'category'])
        if obj.engine_ready != spec['engine_ready']:
            obj.engine_ready = spec['engine_ready']
            fields.append('engine_ready')
        if becoming_ready and not obj.is_active:
            obj.is_active = True
            fields.append('is_active')
        if activate_all and spec['engine_ready'] and not obj.is_active:
            obj.is_active = True
            fields.append('is_active')
        if activate_all:
            if not (obj.short_description or '').strip():
                obj.short_description = spec['short_description']
                fields.append('short_description')
            if not (obj.meta_title or '').strip():
                obj.meta_title = spec['meta_title']
                fields.append('meta_title')
            if not (obj.meta_description or '').strip():
                obj.meta_description = spec['meta_description']
                fields.append('meta_description')
            if not (obj.disclaimer or '').strip():
                obj.disclaimer = spec['disclaimer']
                fields.append('disclaimer')
            if not obj.faq_json:
                obj.faq_json = spec.get('faqs') or []
                fields.append('faq_json')
            if getattr(obj, 'category_id', None) != category.id:
                obj.category = category
                fields.append('category')
        if obj.slug == 'health-insurance-calculator' and obj.title == 'Insurance Premium Calculator':
            obj.title = spec['title']
            obj.short_description = spec['short_description']
            obj.meta_title = spec['meta_title']
            obj.meta_description = spec['meta_description']
            obj.icon_class = spec['icon_class']
            obj.is_active = bool(spec['engine_ready'])
            fields.extend([
                'title', 'short_description', 'meta_title', 'meta_description',
                'icon_class', 'is_active',
            ])
        if getattr(obj, 'category_id', None) is None and category is not None:
            obj.category = category
            fields.append('category')
        if fields:
            fields = list(dict.fromkeys(fields))
            if 'updated_at' in {f.name for f in obj._meta.fields}:
                fields.append('updated_at')
            obj.save(update_fields=fields)
            updated += 1
    return created, updated
