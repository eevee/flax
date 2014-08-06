from collections import defaultdict
from enum import Enum
from functools import partial

import zope.interface as zi

from flax.component import IComponent
from flax.component import ICombatant, Combatant
from flax.component import Solid, Empty
from flax.component import Container
from flax.component import Portable
from flax.component import Equipment
from flax.component import GenericAI, PlayerIntelligence
from flax.component import PortalDownstairs, PortalUpstairs


class Layer(Enum):
    """Vertical positioning of an entity.  Any given tile must have one
    architecture, may have one creature, and can have zero or more items.
    """
    architecture = 1
    item = 2
    creature = 3


class EntityType:
    """A class of entity, except deliberately not implemented as a class.

    Consists primarily of some number of components, each implementing a
    different interface.
    """
    # TODO would be swell to require some components?  e.g. IRender, IPhysics?
    def __init__(self, *components, layer, name, tmp_rendering=None):
        self.layer = layer
        self.name = name
        self.tmp_rendering = tmp_rendering

        self.components = {}
        self.component_data = {}
        for component in components:
            iface = component.interface
            if iface in self.components:
                raise TypeError(
                    "Got two components for the same interface "
                    "({!r}): {!r} and {!r}"
                    .format(iface, self.components[iface], component))
            # Use .component to "unpack" initializers
            self.components[iface] = component.component

            component.init_entity_type(self)

    def __repr__(self):
        return "<{}: {}>".format(type(self).__qualname__, self.name)

    def __call__(self, *args, **kwargs):
        """Create a new entity of this type.  Implemented so you can pretend
        these are classes.
        """
        return Entity(self, *args, **kwargs)

    def __getitem__(self, key):
        return self.component_data[key]

    def __setitem__(self, key, value):
        self.component_data[key] = value


class Entity:
    """An entity in the game world.  Might be anything from a chunk of the
    floor to a segment of a giant worm.
    """
    def __init__(self, type, *initializers):
        # TODO probably just allow kwargs when not ambiguous
        self.type = type
        self.component_data = {}

        # TODO these don't allow two objects to be related in more than one
        # way.  probably want to keep the triples and indexes of them
        # separately?  maybe want a relationship-blob object
        # TODO these names are terribly confusing and i really need a way to
        # make english grammar help me out here
        self.relates_to = defaultdict(set)
        self.related_to = defaultdict(set)

        # Index the initializers by interface
        initializer_map = {}
        for initializer in initializers:
            if initializer.interface in initializer_map:
                raise TypeError(
                    "Constructor for {!r} got two initializers for the same "
                    "interface {!r}: {!r} and {!r}".format(
                        self.type,
                        initializer.interface,
                        initializer.component,
                        initializer_map[initializer.interface].component,
                    )
                )

            initializer_map[initializer.interface] = initializer

        # Call each component as an initializer, allowing the passed-in ones as
        # overrides
        # TODO seems like ComponentAttribute should fall back from the instance
        # to the type, just like python's attribute lookup.  but that doesn't
        # work if everything has to go through the constructor.  or maybe i'm
        # just worrying too much about mem use.
        for interface, component in self.type.components.items():
            if interface in initializer_map:
                initializer = initializer_map.pop(interface)
                if not issubclass(component, initializer.component):
                    raise TypeError(
                        "Constructor for {!r} got an initializer for {!r}, "
                        "which is not a superclass of the actual component "
                        "{!r}".format(
                            self.type,
                            initializer.component,
                            component,
                        )
                    )
            else:
                initializer = component

            try:
                initializer.init_entity(self)
            except Exception:
                # Reraise for context; Python preserves the original
                raise TypeError(
                    "Constructor for {!r} failed to initialize "
                    "{!r} component {!r}"
                    .format(self.type, interface, initializer)
                )

        if initializer_map:
            # TODO run them, or ignore them?
            pass

    def __repr__(self):
        return "<{}: {}>".format(
            type(self).__qualname__,
            self.type.name,
        )

    def __conform__(self, iface):
        # Special z.i method called on an object to ask it to adapt itself to
        # some interface
        # TODO handle keyerror?  or don't?  if not, would be nice to have a
        # better way to ask whether an iface is supported; __contains__?
        component = self.type.components[iface]
        return component.adapt(self)

    # TODO this isn't used any more but i'm keeping it for the TODOs
    def add_modifiers(self, *modifiers):
        # Temporarily inject another source's modifiers onto this thing.
        # TODO: these should know their source and why: (Armor, equipment)
        self.modifiers.extend(modifiers)
        # TODO: fire events when stats change?  (is that how the UI should be
        # updated?)

    def __getitem__(self, key):
        try:
            return self.component_data[key]
        except KeyError:
            return self.type.component_data[key]

    def __setitem__(self, key, value):
        self.component_data[key] = value

    def attach_relation(self, relation):
        reltype = type(relation)
        self.relations[reltype].add(relation)

    def detach_relation(self, relation):
        reltype = type(relation)
        self.relations[reltype].remove(relation)

    def isa(self, entity_type):
        return self.type is entity_type

    @property
    def layer(self):
        return self.type.layer

    def handle_event(self, event):
        for iface, component in self.type.components.items():
            adapted = component.adapt(self)
            adapted.handle_event(event)


###############################################################################
# Sprite and color enumerations.
# These are separate because (a) they naturally get reused a lot among similar
# objects and (b) it becomes considerably easier for another UI implementation
# to swap them out for simpler characters or sprites or whatever.

class Sprite(Enum):
    solid = ' '
    fill = '█'
    floor = '·'
    speckle = '░'
    pillar = '♊'
    fence = '⌗'

    decayed_block = '◾'
    rubble1 = '⬝'
    rubble2 = '⁖'
    rubble3 = '⁘'
    rubble4 = '⁙'
    ruin1a = '▙'
    ruin1b = '▛'
    ruin1c = '▜'
    ruin1d = '▟'
    ruin1e = '█'
    ruin2 = '═'
    ruin3a = '%'
    ruin3b = '#'
    ruin4a = '▖'
    ruin4b = '▗'
    ruin4c = '▘'
    ruin4d = '▝'

    stairs_down = '𝆲'
    stairs_up = '𝆱'
    door_closed = '⌸'
    door_open = '⎕'
    door_locked = '⍯'
    throne = '♄'

    tree = '⯭'
    grass = '⁖'
    tall_grass = 'ʬ'

    flask = 'ð'
    gem = '♦'
    key = '⚷'
    crate = '▥'
    chest = '⏏'
    armor = '['
    shield = '⛉'
    ring = '♁'
    amulet = '♉'

    player = '☻'
    lizard = ':'

    # potential others:
    # ⇭ gravestone
    # ⇶ ammo
    # ⤊ cabin?  uggh too wide barely


class Material(Enum): pass


###############################################################################
# From here on it's all just definitions of specific types.

# -----------------------------------------------------------------------------
# Architecture

from flax.component import Render

Architecture = partial(EntityType, layer=Layer.architecture)

StairsDown = Architecture(
    Empty,
    PortalDownstairs,
    Render(sprite=Sprite.stairs_down, color='stairs'),
    name='stairs',
)
StairsUp = Architecture(
    Empty,
    PortalUpstairs,
    Render(sprite=Sprite.stairs_up, color='stairs'),
    name='stairs',
)
CaveWall = Architecture(
    Solid,
    Render(sprite=Sprite.solid, color='default'),
    name='wall',
)
Wall = Architecture(
    Solid,
    Render(sprite=Sprite.fill, color='wall'),
    name='wall',
)
Floor = Architecture(
    Empty,
    Render(sprite=Sprite.floor, color='floor'),
    name='dirt',
)
Tree = Architecture(
    Solid,
    Render(sprite=Sprite.tree, color='tree'),
    name='tree',
)
Grass = Architecture(
    Empty,
    Render(sprite=Sprite.tall_grass, color='grass'),
    name='grass',
)
CutGrass = Architecture(
    Empty,
    Render(sprite=Sprite.grass, color='grass'),
    name='freshly-cut grass',
)
Dirt = Architecture(
    Empty,
    Render(sprite=Sprite.speckle, color='dirt'),
    name='dirt',
)

from flax.component import Breakable, HealthRender
Rubble = Architecture(
    Empty,
    Breakable(health=10),
    HealthRender(
        (2, Sprite.rubble4, 'decay2'),
        (2, Sprite.rubble3, 'decay2'),
        (2, Sprite.rubble2, 'decay2'),
        (2, Sprite.rubble1, 'decay3'),
    ),
    name='rubble',
)

Ruin = Architecture(
    Solid,
    Breakable(health=10),
    HealthRender(
        (1, Sprite.ruin4a, 'decay3'),
        (1, Sprite.ruin4b, 'decay3'),
        (1, Sprite.ruin4c, 'decay3'),
        (1, Sprite.ruin4d, 'decay3'),
        (5, Sprite.ruin3a, 'decay2'),
        (5, Sprite.ruin3b, 'decay2'),
        (3, Sprite.ruin2, 'decay1'),
        (10, Sprite.ruin1e, 'decay0'),
    ),
    name='ruin',
)


# -----------------------------------------------------------------------------
# Creatures

Creature = partial(EntityType, Solid, Container, layer=Layer.creature)
Player = Creature(
    Combatant(strength=3, health=10),
    PlayerIntelligence,
    Render(sprite=Sprite.player, color='player'),
    name='you',
)
Salamango = Creature(
    Combatant(strength=1, health=5),
    GenericAI,
    Render(sprite=Sprite.lizard, color='salamango'),
    name='salamango',
)


# -----------------------------------------------------------------------------
# Items

Item = partial(EntityType, Portable, layer=Layer.item)

Gem = Item(Render(sprite=Sprite.gem, color='default'), name='gemstone')

# TODO implement a potion!
#Potion = Item(UsablePotion, name='potion', tmp_rendering=('ð', 'default'))
Potion = Item(Render(sprite=Sprite.flask, color='default'), name='potion')

Crate = Item(Container, Render(sprite=Sprite.crate, color='wood'), name='crate')


# TODO not quite sure where this goes.  should it be able to react to events
# too?
class Modifier:
    def __init__(self, stat, add):
        self.stat = stat
        self.add = add

    def modify(self, attr, value):
        if attr is not self.stat:
            return value

        return value + self.add


Armor = Item(
    Equipment(modifiers=[Modifier(ICombatant['strength'], add=3)]),
    Render(sprite=Sprite.armor, color='default'),
    name='armor',
)
