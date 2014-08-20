"""Utility widgets, not really specific to the game."""
import sys

import urwid


class WriteDetectingStream:
    def __init__(self, stream, callback):
        self._stream = stream
        self._pending = None
        self._callback = callback

    def __getattr__(self, attr):
        return getattr(self._stream, attr)

    def write(self, data):
        lines = data.splitlines(True)
        if lines:
            if self._pending:
                lines[0] = self._pending + lines[0]
                self._pending = None
            if not lines[-1].endswith('\n'):
                self._pending = lines.pop()

            for line in lines:
                self._callback(line)

        self._stream.write(data)


class DebugWidget(urwid.ListBox):
    _selectable = False

    def __init__(self):
        super().__init__(urwid.SimpleListWalker([]))

    def activate(self):
        self.orig_stdout = sys.stdout
        self.orig_stderr = sys.stderr

        sys.stdout = WriteDetectingStream(sys.stdout, self.write_stdout)
        sys.stderr = WriteDetectingStream(sys.stderr, self.write_stderr)

    def deactivate(self):
        sys.stdout = self.orig_stdout
        sys.stderr = self.orig_stderr

        del self.orig_stdout
        del self.orig_stderr

    def write_stdout(self, line):
        self.body.append(urwid.Text(('stdout', line.rstrip('\n'))))
        self.set_focus(len(self.body) - 1)

    def write_stderr(self, line):
        self.body.append(urwid.Text(('stderr', line.rstrip('\n'))))
        self.set_focus(len(self.body) - 1)

    def render(self, *a, **kw):
        return super().render(*a, **kw)


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
