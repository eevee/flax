import sys

import urwid

from flax.world import World
from .game import FlaxWidget
from .game import PALETTE


def main():
    world = World()
    widget = FlaxWidget(world)
    loop = urwid.MainLoop(widget, PALETTE)
    # TODO upstream detection for these?
    loop.screen.set_terminal_properties(
        colors=256,
        bright_is_bold=False,
    )
    widget.debug_widget.activate()
    try:
        loop.run()
    except BaseException:
        # Need to unhook sys.stderr BEFORE re-raising, or we'll never see the
        # exception
        widget.debug_widget.deactivate()

        # Also for some reason the exception just sort of vanishes unless we
        # flush right here?
        sys.stdout.flush()
        sys.stderr.flush()

        raise
    else:
        widget.debug_widget.deactivate()
