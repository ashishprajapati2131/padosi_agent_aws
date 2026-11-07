from django import template

register = template.Library()


@register.inclusion_tag("admin/components/pagination.html", takes_context=True)
def admin_pagination(context, page):
    """Pagination links for a Django Page that keep every current filter (URL-encoded).

    The hand-written links used `&search={{ search }}`, which broke on `&`/`#` in a search
    and had to list each filter by name in all 26 templates.
    """
    request = context.get("request")
    params = request.GET.copy() if request is not None else None

    def url(number):
        if params is None:
            return f"?page={number}"
        q = params.copy()
        q["page"] = number
        return "?" + q.urlencode()

    links = []
    if page.has_other_pages():
        for n in page.paginator.get_elided_page_range(page.number, on_each_side=2, on_ends=1):
            links.append({"number": n, "url": url(n) if isinstance(n, int) else None, "current": n == page.number})
    return {
        "page": page,
        "links": links,
        "prev_url": url(page.previous_page_number()) if page.has_previous() else None,
        "next_url": url(page.next_page_number()) if page.has_next() else None,
    }


@register.filter
def any_open(nav_open, names):
    """{% if nav_open|any_open:"admin_a,admin_b" %}: show a sidebar group if any link in it is open."""
    if not nav_open:  # missing from the context (page rendered outside the admin processor)
        return False
    return any(n.strip() in nav_open for n in names.split(",") if n.strip())
