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
    def __init__(self, *components, layer, name, tmp_rendering):
        self.layer = layer
        self.name = name
        self.tmp_rendering = tmp_rendering

        self.components = {}
        for component in components:
            iface = component.interface
            if iface in self.components:
                raise TypeError(
                    "Got two components for the same interface "
                    "({!r}): {!r} and {!r}"
                    .format(iface, self.components[iface], component))
            self.components[iface] = component

    def __repr__(self):
        return "<{}: {}>".format(type(self).__qualname__, self.name)

    def __call__(self, *args, **kwargs):
        """Create a new entity of this type.  Implemented so you can pretend
        these are classes.
        """
        return Entity(self, *args, **kwargs)


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
        # TODO one obvious downside to this: you can't have an entity's
        # initializer only /partly/ override a type's
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
# From here on it's all just definitions of specific types.

# -----------------------------------------------------------------------------
# Architecture

Architecture = partial(EntityType, layer=Layer.architecture)

StairsDown = Architecture(
    Empty,
    PortalDownstairs,
    name='stairs',
    tmp_rendering=('𝆲', 'stairs'))
StairsUp = Architecture(
    Empty,
    PortalUpstairs,
    name='stairs',
    tmp_rendering=('𝆱', 'stairs'))

CaveWall = Architecture(
    Solid,
    name='wall',
    tmp_rendering=(' ', 'default'))
Wall = Architecture(
    Solid,
    name='wall',
    tmp_rendering=('▒', 'default'))
Floor = Architecture(
    Empty,
    name='dirt',
    tmp_rendering=('·', 'floor'))
Tree = Architecture(
    Solid,
    name='tree',
    tmp_rendering=('⯭', 'tree'))
Grass = Architecture(
    Empty,
    name='grass',
    tmp_rendering=('ʬ', 'grass'))
CutGrass = Architecture(
    Empty,
    name='freshly-cut grass',
    tmp_rendering=('░', 'grass'))
Dirt = Architecture(
    Empty,
    name='dirt',
    tmp_rendering=('░', 'dirt'))


# -----------------------------------------------------------------------------
# Creatures

Creature = partial(EntityType, Solid, Container, layer=Layer.creature)
Player = Creature(
    Combatant(strength=3, health=10),
    PlayerIntelligence,
    name='you',
    tmp_rendering=('☻', 'player'))
Salamango = Creature(
    Combatant(strength=1, health=5),
    GenericAI,
    name='salamango',
    tmp_rendering=(':', 'salamango'))


# -----------------------------------------------------------------------------
# Items

Item = partial(EntityType, Portable, layer=Layer.item)

Gem = Item(name='gemstone', tmp_rendering=('♦', 'default'))

# TODO implement a potion!
#Potion = Item(UsablePotion, name='potion', tmp_rendering=('ð', 'default'))
Potion = Item(name='potion', tmp_rendering=('ð', 'default'))

Crate = Item(Container, name='crate', tmp_rendering=('▥', 'wood'))


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
    name='armor',
    tmp_rendering=('[', 'default'),
)
