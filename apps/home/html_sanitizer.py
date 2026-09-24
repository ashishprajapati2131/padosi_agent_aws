"""Remove script-capable markup from admin-authored CMS HTML.

CMS fields (pages, About, coming-soon box, hero heading, plan feature names,
event icons) are rendered as raw HTML. They are written by staff, but a staff
account or an admin-panel XSS must not be able to run JavaScript on public
pages. This keeps every formatting construct the editors use (tags, classes,
inline styles, <style> blocks, SVG icons, images, iframes/embeds, links) and
removes only what can execute script:

- <script>, <object>, <embed>, <applet>, <base>, <meta>, <math>, <plaintext>
- comments / CDATA / processing instructions (parser-differential tricks)
- on* event handler attributes, srcdoc, malformed attribute names
- javascript:/vbscript:/data: URLs (data:image/* is kept on <img src>)
- CSS expression()/javascript:/-moz-binding/behavior in style attrs/blocks

Text without '<' is returned unchanged, so plain-text values render exactly
as before.
"""
import re
from functools import lru_cache

from bs4 import BeautifulSoup
from bs4.element import Comment, CData, Declaration, Doctype, ProcessingInstruction

_DROP_TAGS = frozenset({
    'script', 'object', 'embed', 'applet', 'base', 'meta', 'math', 'plaintext',
})
_SVG_ANIMATION_TAGS = frozenset({'set', 'animate', 'animatemotion', 'animatetransform'})
_URL_ATTRS = frozenset({
    'href', 'src', 'action', 'formaction', 'data', 'poster', 'background',
    'srcset', 'lowsrc', 'dynsrc', 'ping', 'cite', 'longdesc', 'usemap',
    'manifest', 'codebase', 'xlink:href', 'values', 'to', 'from', 'by',
})
_DROP_ATTRS = frozenset({'srcdoc'})
_ATTR_NAME_RE = re.compile(r'^[a-zA-Z_:][-a-zA-Z0-9_:.]*$')
_TAG_NAME_RE = re.compile(r'^[a-zA-Z][a-zA-Z0-9-]*(:[a-zA-Z][a-zA-Z0-9-]*)?$')
_CONTROL_RE = re.compile(r'[\x00-\x20\x7f-\x9f]+')
_BAD_SCHEME_RE = re.compile(r'(javascript|vbscript|livescript|mocha):')
_BAD_CSS_RE = re.compile(r'expression\(|javascript:|vbscript:|-moz-binding|behavior\s*:', re.IGNORECASE)
_STRIP_NODE_TYPES = (Comment, CData, ProcessingInstruction, Declaration, Doctype)


def _normalise(value):
    if isinstance(value, (list, tuple)):
        value = ' '.join(value)
    return _CONTROL_RE.sub('', str(value)).lower()


def _unsafe_url(tag_name, attr_name, value):
    norm = _normalise(value)
    if _BAD_SCHEME_RE.search(norm):
        return True
    if norm.startswith('data:') or ',data:' in norm:
        # Inline images from rich-text editors are harmless in an <img>.
        return not (tag_name in ('img', 'source') and attr_name in ('src', 'srcset')
                    and norm.startswith('data:image/'))
    return False


def _clean_tag(tag):
    name = (tag.name or '').lower()
    for attr in list(tag.attrs):
        lname = attr.lower()
        value = tag.attrs[attr]
        if (
            not _ATTR_NAME_RE.match(attr)
            or lname.startswith('on')
            or lname in _DROP_ATTRS
            or ((lname in _URL_ATTRS or lname.endswith(':href')) and _unsafe_url(name, lname, value))
            or (lname == 'style' and _BAD_CSS_RE.search(_normalise(value)))
        ):
            del tag.attrs[attr]
    if name in _SVG_ANIMATION_TAGS:
        target = _normalise(tag.attrs.get('attributename', ''))
        if target.endswith('href'):
            tag.decompose()
            return
    if name == 'style':
        css = tag.get_text()
        # Inside <svg> a <style> body is parsed as markup by browsers (the
        # Python parser treats it as raw text), and real CSS never contains a
        # literal '<' — such a block can only be an injection attempt.
        if _BAD_CSS_RE.search(css) or '<' in css:
            tag.decompose()


_ACTIVE_TAG_RE = re.compile(r'<\s*/?\s*(script|object|embed|applet)\b', re.IGNORECASE)
_ACTIVE_ATTR_RE = re.compile(r'<[^>]*?[\s/"\'](on[a-z]+|srcdoc)\s*=', re.IGNORECASE)


def _soup_has_active_content(soup):
    for tag in soup.find_all(True):
        name = (tag.name or '').lower()
        if name in ('script', 'object', 'embed', 'applet'):
            return True
        for attr, value in tag.attrs.items():
            lname = attr.lower()
            if lname.startswith('on') or lname == 'srcdoc' or not _ATTR_NAME_RE.match(attr):
                return True
            if (lname in _URL_ATTRS or lname.endswith(':href')) and _BAD_SCHEME_RE.search(_normalise(value)):
                return True
    return False


def has_active_content(value):
    """True if HTML can run script when served as-is (Raw HTML CMS pages).

    Deliberately over-inclusive: it checks the parsed document, the text of
    comments (parser-differential tricks) and the raw/entity-decoded source.
    """
    import html as _html

    text = '' if value is None else str(value)
    if not text:
        return False
    decoded = _html.unescape(text)
    if _ACTIVE_TAG_RE.search(decoded) or _ACTIVE_ATTR_RE.search(decoded):
        return True
    if _BAD_SCHEME_RE.search(_CONTROL_RE.sub('', decoded).lower()):
        return True
    if '<' not in text:
        return False
    soup = BeautifulSoup(text, 'html.parser')
    if _soup_has_active_content(soup):
        return True
    for node in soup.find_all(string=lambda s: isinstance(s, _STRIP_NODE_TYPES)):
        if '<' in node and _soup_has_active_content(BeautifulSoup(str(node), 'html.parser')):
            return True
    return False


@lru_cache(maxsize=1024)
def sanitize_html(value):
    """Return ``value`` with script-capable markup removed (str in, str out)."""
    if value is None:
        return ''
    value = str(value)
    if '<' not in value:
        return value

    soup = BeautifulSoup(value, 'html.parser')

    for node in soup.find_all(string=lambda s: isinstance(s, _STRIP_NODE_TYPES)):
        node.extract()

    for tag in soup.find_all(True):
        if tag.decomposed:
            continue
        if (tag.name or '').lower() in _DROP_TAGS:
            tag.decompose()
        elif not _TAG_NAME_RE.match(tag.name or ''):
            tag.unwrap()

    for tag in soup.find_all(True):
        if not tag.decomposed:
            _clean_tag(tag)

    return str(soup)
