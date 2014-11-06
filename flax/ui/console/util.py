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
        super().__init__(
            None, bottom_w,
            # These get replaced every time; just need some sane defaults
            align='center', valign='middle', height='pack', width='pack',
        )

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

    def _close_handler(self, widget, *args):
        urwid.disconnect_signal(widget, 'close-overlay', self._close_handler)
        self.change_overlay(None)

    def change_overlay(self, widget, **kwargs):
        if widget:
            urwid.disconnect_signal(widget, 'close-overlay', self._close_handler)
            urwid.connect_signal(widget, 'close-overlay', self._close_handler)

            if 'box' in widget.sizing():
                # A box is probably a popup, so center it
                defaults = dict(
                    align='center',
                    valign='middle',
                    width=('relative', 90),
                    height=('relative', 90),
                )
            else:
                # Otherwise it's probably a prompt or something, so stick it at
                # the bottom
                defaults = dict(
                    align='left',
                    valign='bottom',
                    width=('relative', 100),
                    height='pack',
                )

            defaults.update(kwargs)
            self.set_overlay_parameters(**defaults)

        self.top_w = widget
        self._invalidate()
