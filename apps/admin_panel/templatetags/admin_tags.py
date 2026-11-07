from django import template

register = template.Library()


@register.inclusion_tag("admin/components/pagination.html", takes_context=True)
def admin_pagination(context, page, **overrides):
    """Pagination links for a Django Page that keep every current filter (URL-encoded).

    The hand-written links used `&search={{ search }}`, which broke on `&`/`#` in a search
    and had to list each filter by name in all 26 templates.
    overrides force query values, e.g. {% admin_pagination page tab="master" %}.
    """
    request = context.get("request")
    params = request.GET.copy() if request is not None else None

    def url(number):
        if params is None:
            return "?" + "&".join([f"{k}={v}" for k, v in overrides.items()] + [f"page={number}"])
        q = params.copy()
        for key, value in overrides.items():
            q[key] = value
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


class _ModalNode(template.Node):
    def __init__(self, nodelist, modal_id, kwargs):
        self.nodelist, self.modal_id, self.kwargs = nodelist, modal_id, kwargs

    def render(self, context):
        opts = {k: v.resolve(context) for k, v in self.kwargs.items()}
        modal_id = self.modal_id.resolve(context)
        title_id = opts.get("title_id") or f"{modal_id}Title"
        dialog = " ".join(filter(None, [
            "modal-dialog",
            f"modal-{opts['size']}" if opts.get("size") else "",
            "modal-dialog-centered" if opts.get("centered") else "",
            "modal-dialog-scrollable" if opts.get("scrollable") else "",
        ]))
        from django.template.loader import render_to_string

        return render_to_string("admin/components/modal.html", {
            "modal_id": modal_id, "title": opts.get("title", ""), "title_id": title_id,
            "dialog_class": dialog, "body": self.nodelist.render(context),
        })


@register.tag("admin_modal")
def admin_modal(parser, token):
    """{% admin_modal "id" title="..." size="lg" centered=True %} body + footer {% endadmin_modal %}

    Shared Bootstrap modal shell (wrapper, dialog, header with title and close button).
    The body/footer stay in the page, so forms that wrap body and footer keep working.
    """
    bits = token.split_contents()
    if len(bits) < 2:
        raise template.TemplateSyntaxError("admin_modal needs a modal id")
    modal_id = parser.compile_filter(bits[1])
    kwargs = {}
    for bit in bits[2:]:
        key, _, value = bit.partition("=")
        kwargs[key] = parser.compile_filter(value)
    nodelist = parser.parse(("endadmin_modal",))
    parser.delete_first_token()
    return _ModalNode(nodelist, modal_id, kwargs)
