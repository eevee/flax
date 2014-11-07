import logging
import sys

import urwid

from flax.component import GameOver
from flax.world import World
from .game import FlaxWidget
from .game import PALETTE


LEVEL_STDOUT = logging.INFO - 1
LEVEL_STDERR = logging.INFO - 2


class LogWidgetHandler(logging.Handler):
    def __init__(self, *args, widget, **kwargs):
        super().__init__(*args, **kwargs)
        self._widget = widget

    def emit(self, record):
        msg = self.format(record)
        self._widget.add_log_line(msg)


def main():
    # Build the interface
    world = World()
    widget = FlaxWidget(world)
    loop = urwid.MainLoop(widget, PALETTE)
    # TODO upstream detection for these?
    loop.screen.set_terminal_properties(
        colors=256,
        bright_is_bold=False,
    )

    # Add a logging handler that redirects INFO records under the flax
    # namespace into the UI
    flax_logger = logging.getLogger('flax')
    handler = LogWidgetHandler(widget=widget.log_widget)
    flax_logger.addHandler(handler)
    flax_logger.setLevel(logging.INFO)
    flax_logger.propagate = False

    try:
        loop.run()
    except Exception:
        # TODO need to clean up console even for an arbitrary exception?  maybe
        # if i use `with loop.start():`?  i'm surprised run() doesn't clean
        # itself up in a finally block, actually.

        # For reasons beyond my mortal comprehension, the exception gets eaten
        # if I don't flush stderr and then reraise it.
        sys.stdout.flush()
        sys.stderr.flush()
        raise

    # If the world captured an explicit end-of-game, print the message before
    # dying entirely.
    if world.obituary:
        print(world.obituary.message)
