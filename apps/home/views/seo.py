from django.http import HttpResponse

def robots_txt(request):
    lines = [
        "User-agent: *",
        "Disallow: /django-admin/",
        "Disallow: /agent-login/",
        "Disallow: /agent/dashboard/",
        "Disallow: /insurance-login/",
        "Disallow: /media/app/private/",
        "Disallow: /api/",
        "",
        f"Sitemap: {request.build_absolute_uri('/sitemap.xml')}"
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")
