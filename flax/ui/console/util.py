"""Utility widgets, not really specific to the game."""
import sys

import urwid


class LogWidget(urwid.ListBox):
    # Can't receive focus on its own; assumed that some parent widget will
    # worry about scrolling us
    _selectable = False

    def __init__(self):
        super().__init__(urwid.SimpleListWalker([]))

    def add_log_line(self, line):
        text = urwid.Text(('log-game', line))
        self.body.append(text)
        self.focus_position = len(self.body) - 1


class ToggleableOverlay(urwid.Overlay):
    """An Overlay where the top widget can be swapped out or hidden entirely.

    If the top widget is removed, focus passes to the bottom widget.
    """
    def __init__(self, bottom_w):
        # TODO uhh what are good defaults??
        super().__init__(None, bottom_w, align='center', width=('relative', 90), valign='middle', height=('relative', 90))

    def selectable(self):
        return self.focus.selectable()

    def keypress(self, size, key):
        if self.top_w:
            return super().keypress(size, key)
        else:
            return self.bottom_w.keypress(size, key)

    @property
    def focus(self):
        if self.top_w:
            return self.top_w
        else:
            return self.bottom_w

    @property
    def focus_position(self):
        if self.top_w:
            return 1
        else:
            return 0

    @focus_position.setter
    def focus_position(self, position):
        if position == 0:
            self.top_w = None
        else:
            super().focus_position = position

    # TODO override `contents` to return a 1-element thing

    def render(self, size, focus=False):
        if self.top_w:
            return super().render(size, focus)
        else:
            return self.bottom_w.render(size, focus)

    ### New APIs

    def change_overlay(self, widget):
        self.top_w = widget
        self._invalidate()
