"""Searchable terminal picker; session discovery refreshes while it is open."""

import asyncio
from collections.abc import Callable
from datetime import datetime

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style
from prompt_toolkit.utils import get_cwidth
from prompt_toolkit.widgets import TextArea

from .sessions import Session, clean_label


def _fit(text: str, width: int) -> str:
    result, used = "", 0
    for char in text:
        size = get_cwidth(char)
        if used + size > width - 1:
            return result + "…"
        result += char
        used += size
    return result


def choose_session(load: Callable[[], list[Session]], initial: list[Session]) -> Session | None:
    sessions = initial
    selected_id = initial[0].id if initial else None
    query = TextArea(height=1, prompt="Search: ", multiline=False)
    bindings = KeyBindings()
    refresh_error = ""

    def matches():
        words = query.text.casefold().split()
        return [
            item
            for item in sessions
            if all(word in f"{item.title} {item.id} {item.cwd}".casefold() for word in words)
        ]

    def current_index(items):
        return next((i for i, item in enumerate(items) if item.id == selected_id), 0)

    def rows():
        items = matches()
        height = max(3, app.output.get_size().rows - 7)
        width = max(20, app.output.get_size().columns - 4)
        selected = current_index(items)
        start = max(0, selected - height + 1)
        if not items:
            return [("class:muted", "No matching conversations. The list refreshes automatically.")]
        output = []
        for i, item in enumerate(items[start : start + height], start):
            marker = "❯ " if i == selected else "  "
            when = datetime.fromtimestamp(item.updated).strftime("%Y-%m-%d %H:%M")
            text = _fit(f"{item.title}  ·  {when}  ·  {clean_label(str(item.cwd))}", width - 2)
            output.append(("class:selected" if i == selected else "", marker + text + "\n"))
        return output

    def move(amount):
        nonlocal selected_id
        items = matches()
        if items:
            selected_id = items[(current_index(items) + amount) % len(items)].id

    @bindings.add("up")
    def up(event):
        move(-1)

    @bindings.add("down")
    def down(event):
        move(1)

    @bindings.add("enter")
    def enter(event):
        items = matches()
        if items:
            event.app.exit(result=items[current_index(items)])

    @bindings.add("escape")
    @bindings.add("c-c")
    @bindings.add("c-d")
    def cancel(event):
        event.app.exit(result=None)

    async def refresh():
        nonlocal sessions, refresh_error
        while True:
            await asyncio.sleep(2)
            try:
                sessions = await asyncio.to_thread(load)
                refresh_error = ""
            except OSError:
                refresh_error = " · Refresh unavailable; retrying"
            app.invalidate()

    app: Application = Application(
        layout=Layout(
            HSplit(
                [
                    Window(FormattedTextControl("Select a Codex conversation"), height=2),
                    query,
                    Window(height=1),
                    Window(FormattedTextControl(rows)),
                    Window(
                        FormattedTextControl(
                            lambda: (
                                f"{len(matches())} sessions · ↑↓ select · Enter view"
                                f" · Esc cancel{refresh_error}"
                            )
                        ),
                        height=1,
                        style="class:muted",
                    ),
                ]
            ),
            focused_element=query,
        ),
        key_bindings=bindings,
        style=Style.from_dict({"selected": "reverse bold", "muted": "#888888"}),
        full_screen=True,
    )
    return app.run(pre_run=lambda: app.create_background_task(refresh()))
