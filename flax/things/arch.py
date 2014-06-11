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

    def __conform__(self, iface):
        # z.i method called on an object to ask it to adapt itself to some
        # interface
        # TODO handle keyerror?  or don't?
        component = self._type.components[iface]
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


@zi.implementer(IComponent)
class Component(metaclass=ComponentMeta):
    def __init__(self, iface, entity):
        self.iface = iface
        self.entity = entity

    def __getattr__(self, key):
        # TODO keyerror?  or let it raise?
        attr = self.iface[key]
        if isinstance(attr, zi.interface.Method):
            raise AttributeError("missing method??")
        elif isinstance(attr, zi.Attribute):
            return self.entity._component_data[attr]
        else:
            # TODO ???  can this happen.  also are there other Attributes
            raise AttributeError("wat")

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


Creature = partial(ThingType, Solid, layer=Layer.creature)

Player = Creature(tmp_rendering=('☻', 'player'))

Salamango = Creature(tmp_rendering=(':', 'salamango'))



Item = partial(ThingType, layer=Layer.item)


class IUsable(IComponent):
    def use():
        pass


@zi.implementer(IUsable)
class UsablePotion(Component):
    def use(self):
        return effect.Heal()

#potion = Item(UsablePotion, name="potion")
