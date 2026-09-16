"""Safe Markdown plus math delimiters for locally served MathJax."""

import html

from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.texmath import texmath_plugin
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

_PYGMENTS_FORMATTER = HtmlFormatter(nowrap=True)


def _math(self, tokens, index, options, env):
    token = tokens[index]
    display = token.type.startswith("math_block") or token.type == "math_inline_double"
    tag, opening, closing = ("div", r"\[", r"\]") if display else ("span", r"\(", r"\)")
    return f'<{tag} class="math">{opening}{html.escape(token.content)}{closing}</{tag}>'


def _highlight(source: str, language: str, _attributes: str) -> str:
    if not language:
        return ""
    try:
        lexer = get_lexer_by_name(language)
    except ClassNotFound:
        return ""
    rendered = highlight(source, lexer, _PYGMENTS_FORMATTER)
    canonical = html.escape(lexer.name, quote=True)
    original = html.escape(language, quote=True)
    return (
        f'<pre class="highlight" data-language="{canonical}">'
        f'<code class="language-{original}">{rendered}</code></pre>'
    )


def make_renderer() -> MarkdownIt:
    renderer = (
        MarkdownIt("commonmark", {"html": False, "highlight": _highlight})
        .enable("table")
        .enable("strikethrough")
    )
    renderer.use(texmath_plugin, delimiters="brackets")
    renderer.use(dollarmath_plugin, allow_labels=False, allow_space=False, allow_digits=False)
    for name in ("math_inline", "math_inline_double", "math_block", "math_block_eqno"):
        renderer.add_render_rule(name, _math)
    return renderer
