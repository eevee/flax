from collections import defaultdict
from enum import Enum
from functools import partial

import zope.interface as zi


class Layer(Enum):
    architecture = 1
    item = 2
    creature = 3


class ThingType:
    def __init__(self, *components, layer, tmp_rendering):
        self.layer = layer
        self.tmp_rendering = tmp_rendering

        self.components = {}
        for component in components:
            for iface in zi.implementedBy(component):
                if iface is IComponent:
                    continue
                if iface in self.components:
                    raise TypeError(
                        "Got two components for the same interface "
                        "({!r}): {!r} and {!r}"
                        .format(iface, self.components[iface], component))
                self.components[iface] = component

    def __call__(self, *args, **kwargs):
        return Thing(self, *args, **kwargs)


class Thing:
    def __init__(self, type):
        self.type = type
        self.component_data = {}

    def __conform__(self, iface):
        # z.i method called on an object to ask it to adapt itself to some
        # interface
        # TODO handle keyerror?  or don't?
        component = self.type.components[iface]
        return component(iface, self)

    def isa(self, thing_type):
        # TODO unclear how this will handle inherited properties, or if it ever
        # needs to (well, surely we want e.g. Potion)
        return self.type is thing_type

    @property
    def layer(self):
        return self.type.layer

    def handle_event(self, event):
        for iface, component in self.type.components.items():
            component(iface, self).handle_event(self, event)




class Handler:
    @classmethod
    def wrap(cls, func, event_class):
        if isinstance(func, Handler):
            func.add(event_class)
            return func
        else:
            return cls(func, event_class)

    def __init__(self, func, event_class):
        self.func = func
        self.event_classes = [event_class]

    def add(self, event_class):
        self.event_classes.append(event_class)

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)


def handler(event_class):
    def decorator(f):
        return Handler.wrap(f, event_class)

    return decorator

class IComponent(zi.Interface):
    pass


class ComponentMeta(type):
    def __new__(meta, name, bases, attrs):
        event_handlers = defaultdict(list)

        for key, value in list(attrs.items()):
            if isinstance(value, Handler):
                for cls in value.event_classes:
                    event_handlers[cls].append(value.func)

                del attrs[key]

        # TODO should this automatically include bases' handlers?
        attrs['event_handlers'] = event_handlers

        return super().__new__(meta, name, bases, attrs)


class ComponentAttribute:
    def __init__(desc, zope_attribute, initializer):
        desc.zope_attribute = zope_attribute
        desc.initializer = initializer

    def __get__(desc, self, cls):
        if self is None:
            return desc

        # TODO how does this get set initially, though...
        attr = desc.zope_attribute
        data = self.entity.component_data

        if attr not in data:
            data[attr] = desc.initializer(self)

        return data[attr]

    def __set__(desc, self, value):
        self.entity.component_data[desc.zope_attribute] = value


def attribute(iface):
    def decorator(f):
        return ComponentAttribute(iface[f.__name__], f)
    return decorator


@zi.implementer(IComponent)
class Component(metaclass=ComponentMeta):
    def __init__(self, iface, entity):
        self.iface = iface
        self.entity = entity

    def handle_event(self, thing, event):
        # TODO seems a bit odd that we're receiving the actual Thing here
        # TODO what order should these be called in?
        for event_class in type(event).__mro__:
            for handler in self.event_handlers[event_class]:
                # TODO at this point we are nested three loops deep
                handler(thing, event)



class IPhysics(IComponent):
    def blocks(actor):
        """Return True iff this object won't allow `actor` to move on top of
        it.
        """


from flax.event import Walk

@zi.implementer(IPhysics)
class Solid(Component):
    def blocks(self, actor):
        # TODO i have /zero/ idea how passwall works here
        return True

    # TODO there's a fuzzy line here.  what's the difference between a
    # component method and an event handler?  shouldn't *any* IPhysics object
    # respond to Walk?  isn't that the whole point of a physical object?
    # obviously there should be support for exceptions, but i feel like
    # requiring a component implementation to respond to default events (and
    # perhaps even associating each event with a specific interface somehow)
    # would make this all make a bit more...  predictable
    # TODO also seems like i should /require/ that every ThingType has a
    # IPhysics, maybe others...
    @handler(Walk)
    def handle_walk(thing, event):
        event.cancel()



@zi.implementer(IPhysics)
class Empty(Component):
    def blocks(self, actor):
        return False

    @handler(Walk)
    def handle_walk(thing, event):
        pass


class ICombatant(IComponent):
    """Implements an entity's ability to fight and take damage."""
    health = zi.Attribute("""Entity's health meter.""")

    def damage(amount):
        """Take damage.

        Don't override this to respond to damage; handle the Damage event
        instead.
        """


@zi.implementer(ICombatant)
class Combatant(Component):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @attribute(ICombatant)
    def health(self):
        return 10

    def damage(self, amount):
        self.health -= amount
        # XXX uhhhh how do i fire events from arbitrary places goddammit




class IActor(IComponent):
    """Implements an entity's active thought process.  An entity with an
    `IActor` component can decide to perform actions on its own, and has a
    sense of speed and time.
    """
    def act():
        """Return an action to be performed (i.e., an `Event` to be fired), or
        `None` to do nothing.
        it.
        """


@zi.implementer(IActor)
class GenericAI(Component):
    def act(self):
        from flax.geometry import Direction
        from flax.event import Walk
        import random
        return Walk(self.entity, random.choice(list(Direction)))


@zi.implementer(IActor)
class PlayerIntelligence(Component):
    def act(self):
        return None


Architecture = partial(ThingType, layer=Layer.architecture)

CaveWall = Architecture(
    Solid,
    tmp_rendering=(' ', 'default'))
Wall = Architecture(
    Solid,
    tmp_rendering=('▒', 'default'))
Floor = Architecture(
    Empty,
    tmp_rendering=('·', 'floor'))
Tree = Architecture(
    Solid,
    tmp_rendering=('↟', 'grass'))
Grass = Architecture(
    Empty,
    tmp_rendering=('ʬ', 'grass'))
CutGrass = Architecture(
    Empty,
    tmp_rendering=('░', 'grass'))
Dirt = Architecture(
    Empty,
    tmp_rendering=('░', 'dirt'))


Creature = partial(ThingType, Solid, Combatant, layer=Layer.creature)

Player = Creature(PlayerIntelligence, tmp_rendering=('☻', 'player'))

Salamango = Creature(GenericAI, tmp_rendering=(':', 'salamango'))



Item = partial(ThingType, layer=Layer.item)


class IUsable(IComponent):
    def use():
        pass


@zi.implementer(IUsable)
class UsablePotion(Component):
    def use(self):
        return effect.Heal()

#potion = Item(UsablePotion, name="potion")
