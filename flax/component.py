from collections import defaultdict

import zope.interface as zi

from flax.event import PickUp
from flax.event import MeleeAttack, Damage, Die
from flax.event import Walk
from flax.event import Equip
from flax.event import Unequip

from flax.relation import Wears


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


# TODO: i feel like instead of having two of every event, i'd kind of like to
# have events fire in two passes: during the first, any handler can cancel the
# event or succeed the event, either of which stops further processing; during
# the second, any handler can respond to the success of the event.
# so the base Equipment can have an Equip handler that just equips it and adds
# modifiers; if you want to make armor that sometimes can't be equipped, you
# add a regular first-pass handler that can cancel, but if you want armor that
# does something extra /after/ it's equipped successfully, you do second-pass.
# and then if nothing calls .succeed(), the event is assumed to have failed,
# which would also help prevent a few kinds of mistakes i've already made oops.
# but then, that might only work if both the actor and the target get to
# respond?  i.e. you fire Drink at a potion, but if you have some armor that
# does something with potions, its event handlers are attached to /you/ rather
# than to all potions everywhere.  maybe that's just part of the idea of having
# event handlers from different 'directions' though??
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

        value = data[attr]

        # TODO well this is a bit cumbersome
        for reltype, relations in self.entity.relations.items():
            for relation in relations:
                if self.entity is relation.to_entity:
                    continue
                for mod in relation.to_entity.type.modifiers:
                    value = mod.modify(attr, value)

        return value

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

    def handle_event(self, event):
        # TODO what order should these be called in?
        for event_class in type(event).__mro__:
            for handler in self.event_handlers[event_class]:
                # TODO at this point we are nested three loops deep
                handler(self, event)


###############################################################################
# Particular interfaces and components follow.

# -----------------------------------------------------------------------------
# Physics

class IPhysics(IComponent):
    def blocks(actor):
        """Return True iff this object won't allow `actor` to move on top of
        it.
        """


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
    # would make this all make a bit more...  predictable.  and i think that
    # would make the semantics a little better: most events are, in a way,
    # really just calls to component methods that other things can twiddle
    # TODO also seems like i should /require/ that every entity type has a
    # IPhysics, maybe others...
    @handler(Walk)
    def handle_walk(self, event):
        event.cancel()


@zi.implementer(IPhysics)
class Empty(Component):
    def blocks(self, actor):
        return False

    @handler(Walk)
    def handle_walk(self, event):
        event.world.current_map.move(event.actor, event.target.position)


# -----------------------------------------------------------------------------
# Containment

class IContainer(IComponent):
    inventory = zi.Attribute("""Items contained by this container.""")


@zi.implementer(IContainer)
class Container(Component):
    @attribute(IContainer)
    def inventory(self):
        return []


# -----------------------------------------------------------------------------
# Combat

class ICombatant(IComponent):
    """Implements an entity's ability to fight and take damage."""
    health = zi.Attribute("""Entity's health meter.""")
    strength = zi.Attribute("""Generic placeholder stat while I figure stuff out.""")


@zi.implementer(ICombatant)
class Combatant(Component):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @attribute(ICombatant)
    def health(self):
        return 10

    @attribute(ICombatant)
    def strength(self):
        return 3

    @handler(Damage)
    def handle_damage(self, event):
        self.health -= event.amount

        if self.health <= 0:
            event.world.queue_immediate_event(Die(self.entity))

    @handler(MeleeAttack)
    def handle_attack(self, event):
        print("{0} hits {1}".format(event.actor.type.name, self.entity.type.name))

        # TODO what's the amount
        event.world.queue_immediate_event(Damage(self.entity, 5))

    @handler(Die)
    def handle_death(self, event):
        # TODO player death is different; probably raise an exception for the
        # ui to handle?
        print("{} has died".format(self.entity.type.name))
        event.world.current_map.remove(self.entity)
        # TODO and drop inventory, and/or a corpse


# -----------------------------------------------------------------------------
# AI

class IActor(IComponent):
    """Implements an entity's active thought process.  An entity with an
    `IActor` component can decide to perform actions on its own, and has a
    sense of speed and time.
    """
    def act(world):
        """Return an action to be performed (i.e., an `Event` to be fired), or
        `None` to do nothing.
        it.
        """


@zi.implementer(IActor)
class GenericAI(Component):
    def act(self, world):
        from flax.geometry import Direction
        from flax.event import Walk
        from flax.event import MeleeAttack
        import random
        pos = world.current_map.find(self.entity).position
        player_pos = world.current_map.find(world.player).position
        for direction in Direction:
            if pos + direction == player_pos:
                world.queue_event(MeleeAttack(self.entity, direction))
                return

        # TODO try to walk towards player
        world.queue_event(Walk(self.entity, random.choice(list(Direction))))


@zi.implementer(IActor)
class PlayerIntelligence(Component):
    def act(self, world):
        if world.player_action_queue:
            world.queue_immediate_event(world.player_action_queue.popleft())


# -----------------------------------------------------------------------------
# Items

class IPortable(IComponent):
    """Entity can be picked up and placed in containers."""


@zi.implementer(IPortable)
class Portable(Component):
    # TODO maybe "actor" could just be an event target, and we'd need fewer
    # duplicate events for the source vs the target?
    @handler(PickUp)
    def handle_picked_up(self, event):
        from flax.entity import Layer
        print("ooh picking up", self.entity.type.name)
        assert self.entity.type.layer is Layer.item
        event.world.current_map.remove(self.entity)
        IContainer(event.actor).inventory.append(self.entity)


# -----------------------------------------------------------------------------
# Equipment

class IEquipment(IComponent):
    pass


@zi.implementer(IEquipment)
class Equipment(Component):
    @handler(Equip)
    def handle_equip(self, event):
        print("you put on the armor")
        Wears(event.actor, self.entity)

    @handler(Unequip)
    def handle_unequip(self, event):
        print("you take off the armor")
        for relation in list(self.entity.relations[Wears]):
            # TODO again this has the problem of direction, ugh
            relation.destroy()

    #@handler(Damage, on=wearer)
    #def handle_wearer_damage(self, event):
    pass
