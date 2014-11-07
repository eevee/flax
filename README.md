# flax

This is the beginnings of a roguelike, set in the [Flora](http://floraverse.com/) universe.

You will need:

* **Python 3.3+**.  Python 2 does not and will never work.
    * `urwid`
    * `zope.interface`
    * `enum34` (if you're using Python 3.3)

* **A Unix-like terminal.**  My dev environment is Linux, but flax should work fine in OS X or Cygwin or similar.  It _will not_ work in the Windows console.  I also _strongly suggest_ you use a terminal emulator that supports 256 colors.

* **A monospace Unicode font.**  flax uses text graphics, but it does not (currently) restrict itself to ASCII.  I've limited myself to characters that actually fit within a character cell, and I _believe_ Bitstream Vera Sans Mono and DejaVu Sans Mono include all the glyphs I use.  I'm interested to hear if particular objects give you trouble, but I don't intend to look into font support too deeply while the game is still in flux.

If you don't know the Python ecosystem, you can pretty much just do this (assuming you have Python 3 and [pip](http://pip-installer.org/) already):

    $ pip install --user -e git+https://github.com/eevee/flax#egg=flax
    $ flax

Or you can run directly from a source checkout with:

    python -m flax

Note that you may need to use `pip3` and `python3` above, if Python 3 is not the default Python on your system.


## Keys

The arrow keys move in the four cardinal directions.  You can also use the numpad to move diagonally.

If you try to move into a monster, you will attack it.  If you try to move into a door, you will open it.

Key     | Function
---     | --------
`>`     | go down (stairs, etc.)
`<`     | go up (stairs, etc.)
`,`     | pick up items
`i`     | view inventory
`q`     | quit
