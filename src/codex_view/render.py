"""Safe Markdown plus math delimiters for locally served MathJax."""

import html

from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.texmath import texmath_plugin


def _math(self, tokens, index, options, env):
    token = tokens[index]
    display = token.type.startswith("math_block") or token.type == "math_inline_double"
    tag, opening, closing = ("div", r"\[", r"\]") if display else ("span", r"\(", r"\)")
    return f'<{tag} class="math">{opening}{html.escape(token.content)}{closing}</{tag}>'


def make_renderer() -> MarkdownIt:
    renderer = MarkdownIt("commonmark", {"html": False}).enable("table").enable("strikethrough")
    renderer.use(texmath_plugin, delimiters="brackets")
    renderer.use(dollarmath_plugin, allow_labels=False, allow_space=False, allow_digits=False)
    for name in ("math_inline", "math_inline_double", "math_block", "math_block_eqno"):
        renderer.add_render_rule(name, _math)
    return renderer
