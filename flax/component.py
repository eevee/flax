"""Component infrastructure and definitions.

Game world objects are called "entities", and are broken into parts that each
implement some interface (and respond to some events).  This allows different
types of entities to share only some of their behavior, without making an
unholy mess of mixins and inheritance.

Each part is called a "component", which is what's defined here.  See the
`Component` base class for an explanation of how they work, or just read over
some of the component classes to get a feel for what's going on.
"""
from collections import defaultdict
import logging

import zope.interface as zi

from flax.event import PickUp
from flax.event import MeleeAttack, Damage, Die
from flax.event import Ascend, Descend, Walk
from flax.event import Open, Unlock
from flax.event import Equip
from flax.event import Unequip

from flax.relation import RelationSubject
from flax.relation import RelationObject
from flax.relation import Wearing


log = logging.getLogger(__name__)


###############################################################################
# Crazy plumbing begins here!

# -----------------------------------------------------------------------------
# Component definitions

# TODO distinguish between those that should only be altered with modifiers
# (like stats), and those that are expected to change (like /current/ health
# and inventory)?
def static_attribute(doc):
    attr = zi.Attribute(doc)
    attr.setTaggedValue('mode', 'static')
    return attr


# TODO none of these yet, but we should assert that they /are/ given as
# properties of the class
def derived_attribute(doc):
    attr = zi.Attribute(doc)
    attr.setTaggedValue('mode', 'derived')
    return attr


class IComponentFactory(zi.Interface):
    """An object that produces components.  Usually these are component
    classes, but sometimes they're wrapped in a `ComponentInitializer`.
    """
    interface = zi.Attribute("The interface this component implements.")
    component = zi.Attribute("The real underlying component class.")

    def init_entity_type(entity_type):
        """Run the component's `__typeinit__` on the given entity type."""

    def init_entity(entity):
        """Run the component's `__init__` on the given entity."""

    def adapt(entity):
        """Create a component that wraps the given entity.

        This is the actual component constructor, since calling is used for
        something else.
        """


@zi.implementer(IComponentFactory)
class ComponentInitializer:
    """What you get when you call a component class.  Used as a deferred init
    mechanism.
    """
    def __init__(self, component, args, kwargs):
        self.component = component
        self.args = args
        self.kwargs = kwargs

    @property
    def interface(self):
        return self.component.interface

    def init_entity_type(self, entity):
        self.component.init_entity_type(entity, *self.args, **self.kwargs)

    def init_entity(self, entity):
        self.component.init_entity(entity, *self.args, **self.kwargs)

    def adapt(self, entity):
        return self.component.adapt(entity)


@zi.implementer(IComponentFactory)
class ComponentMeta(type):
    """Metaclass for components.  Implements the slightly weird bits, like the
    ruination of object creation.  See `Component` for most of it.

    Note that calling a component class does NOT produce component objects --
    it produces objects used for initializing entities later.  Component
    objects are created with `adapt`.
    """
    def __new__(meta, name, bases, attrs, *, interface=None):
        # Prevent assigning to arbitrary attributes, cut down on storage space
        # a bit, and make object creation (which we do a lot!) a bit faster
        attrs.setdefault('__slots__', ())

        return super().__new__(meta, name, bases, attrs)

    def __init__(cls, name, bases, attrs, *, interface=None):
        if interface is None:
            # Try to fetch it from a parent class
            interface = cls.interface

        zi.implementer(interface)(cls)
        cls.interface = interface

        # Slap on an attribute descriptor for every static attribute in the
        # interface.  (Derived attributes promise that they're computed by the
        # class via @property or some other mechanism.)
        for key in interface:
            attr = interface[key]
            if not isinstance(attr, zi.Attribute):
                continue

            mode = attr.queryTaggedValue('mode')
            if mode == 'static':
                if key in cls.__dict__:
                    # TODO i have seen the light: there is a good reason to do
                    # this.  see HealthRender
                    continue
                    raise TypeError(
                        "Implementation {!r} "
                        "defines static attribute {!r}"
                        .format(cls, key)
                    )
                else:
                    setattr(cls, key, ComponentAttribute(attr))

    def __call__(cls, *args, **kwargs):
        """Override object construction.  We don't want to make a component
        object; we want to make something that can be used to initialize an
        entity later.  That something is a `ComponentInitializer`.
        """
        return ComponentInitializer(cls, args, kwargs)

    def init_entity(cls, entity, *args, **kwargs):
        """Initialize an entity.  Calls the class's ``__init__`` method."""
        if cls.__init__ is Component.__init__:
            # Micro-optimization: if there's no __init__, don't even try to
            # call it
            return
        self = cls.adapt(entity)
        self.__init__(*args, **kwargs)

    def init_entity_type(cls, entity_type, *args, **kwargs):
        """Initialize an entity.  Calls the class's ``__typeinit__`` method."""
        # TODO self.entity will actually be the class here which seems mega
        # janky.
        if cls.__typeinit__ is Component.__typeinit__:
            # Micro-optimization: if there's no __typeinit__, don't even try to
            # call it
            return
        # This is a slightly naughty use of `adapt`, since we're not passing an
        # entity, but EntityType has the same plumbing so it all works.
        self = cls.adapt(entity_type)
        self.__typeinit__(*args, **kwargs)

    def adapt(cls, entity):
        """The actual constructor.  Creates a new component that wraps the
        given entity.  Does not call ``__init__``.
        """
        self = object.__new__(cls)
        self.entity = entity
        return self

    @property
    def component(cls):
        return cls


class ComponentAttribute:
    def __init__(desc, zope_attribute):
        desc.zope_attribute = zope_attribute

    def __get__(desc, self, cls):
        if self is None:
            return desc

        attr = desc.zope_attribute
        try:
            value = self.entity[attr]
        except KeyError:
            raise AttributeError

        # TODO this doesn't seem right really.  i think modifiers should really
        # be tracked separately, and removed by the relation destructor
        for relation_set in self.entity.relates_to.values():
            for relation in relation_set:
                # TODO lol yeah this definitely won't work
                for mod in IEquipment(relation.to_entity).modifiers:
                    value = mod.modify(attr, value)

        return value

    def __set__(desc, self, value):
        # TODO seems like this doesn't make sense for something subject to
        # modifiers?
        self.entity.component_data[desc.zope_attribute] = value


class IComponent(zi.Interface):
    """Dummy base class for all component interfaces.

    A component interface specifies some small set of data and behavior that an
    entity might like to have.  For example, there's an `IActor` interface that
    has a method, ``act``, for deciding what an entity might want to do.  There
    are two basic implementations of this interface: one for monsters where the
    ``act`` method implements an AI, and one for the player where the ``act``
    method merely returns an action based on player input.

    By breaking functionality into discrete components, different entity types
    can share some behavior (such as collision detection) without having to
    share all of it (such as AI).

    Component interfaces also specify what data may be stored on the entity.
    Place a `static_attribute` in your interface's class body, and your
    components will be able to read to and write from an attribute of that
    name.  You don't have to worry about name collisions between different
    interfaces, either.

    An entity type can only have at most one component per interface at a time.

    Interfaces are also used to access components.  If you have an entity, and
    you want its implementation of ``IFoo``, calling ``IFoo(entity)`` will
    produce an appropriate component object.
    """


class Component(metaclass=ComponentMeta, interface=IComponent):
    """Base class for all components.  Take note: some unorthodox things are
    happening here.

    A component class must implement exactly one interface, specified by the
    ``interface`` kwarg in the class statement.  (The interface is inherited by
    subclasses.)

    A component object acts like a "view" of an entity, able to access only the
    data specified in its interface (via `static_attribute`).  That is, within
    a component method, ``self.prop`` will read from and write to a value
    stored within the underlying entity.  The entity itself is also available,
    as ``self.entity``.

    Components aren't created the traditional way.  Instead, they're built to
    act like part of an entity as transparently as possible.  Consider:

        class ICombatant(IComponent):
            strength = static_attribute("Raw power")

        class Combatant(Component, interface=ICombatant):
            def __init__(self, *, strength):
                self.strength = strength

        newt = EntityType(Combatant(strength=3))
        mind_flayer = EntityType(Combatant(strength=100))

    The ``__init__`` method will never actually be called by this code.  It's
    only called when a ``newt`` or ``mind_flayer`` entity is created, to
    initialize the combat part of that entity.  Creating an entity thus
    triggers the ``__init__`` for each of its components, as though the entity
    were all of those components simultaneously.
    """
    # Note: the constructor is ComponentMeta.adapt, which also assigns the
    # `entity` attribute.
    __slots__ = ('entity',)

    def __typeinit__(self):
        pass

    def __init__(self):
        pass

    def __setattr__(self, key, value):
        # TODO this approach will break inheriting ad hoc attributes in
        # subclasses; is that a concern?
        cls = type(self)
        if hasattr(cls, key):
            super().__setattr__(key, value)
        else:
            self.entity[cls, key] = value

    def __getattr__(self, key):
        cls = type(self)
        try:
            return self.entity[cls, key]
        except KeyError:
            raise AttributeError


###############################################################################
# Particular interfaces and components follow.

# -----------------------------------------------------------------------------
# Rendering

class IRender(IComponent):
    # TODO consolidate these into a single some-kind-of-object
    sprite = static_attribute("")
    color = static_attribute("")


class Render(Component, interface=IRender):
    def __typeinit__(self, sprite, color):
        self.sprite = sprite
        self.color = color


class OpenRender(Component, interface=IRender):
    def __typeinit__(self, *, open, closed, locked):
        self.open = open
        self.closed = closed
        self.locked = locked

    @property
    def sprite(self):
        # TODO what if it doesn't exist
        if ILockable(self.entity).locked:
            return self.locked[0]
        # TODO what if it doesn't exist
        elif IOpenable(self.entity).open:
            return self.open[0]
        else:
            return self.closed[0]

    @property
    def color(self):
        # TODO what if it doesn't exist
        if ILockable(self.entity).locked:
            return self.locked[1]
        # TODO what if it doesn't exist
        elif IOpenable(self.entity).open:
            return self.open[1]
        else:
            return self.closed[1]


class HealthRender(Component, interface=IRender):
    def __typeinit__(self, *choices):
        self.choices = []

        total_weight = sum(choice[0] for choice in choices)
        for weight, sprite, color in choices:
            self.choices.append((weight / total_weight, sprite, color))

    def current_rendering(self):
        health = (
            ICombatant(self.entity).current_health /
            ICombatant(self.entity).maximum_health)
        for weight, sprite, color in self.choices:
            if health <= weight:
                return sprite, color
            health -= weight

    @property
    def sprite(self):
        return self.current_rendering()[0]

    @property
    def color(self):
        return self.current_rendering()[1]


# -----------------------------------------------------------------------------
# Physics

class IPhysics(IComponent):
    def blocks(actor):
        """Return True iff this object won't allow `actor` to move on top of
        it.
        """


# TODO i'm starting to think it would be nice to eliminate the dummy base class
# i have for like every goddamn component?  but how?
# TODO seems like i should /require/ that every entity type has a IPhysics,
# maybe others...
class Physics(Component, interface=IPhysics):
    pass


class Solid(Physics):
    def blocks(self, actor):
        # TODO i have /zero/ idea how passwall works here -- perhaps objects
        # should be made of distinct "materials"...
        return True


class Empty(Physics):
    def blocks(self, actor):
        return False


class DoorPhysics(Physics):
    def blocks(self, actor):
        return not IOpenable(self.entity).open


@Walk.check(Solid)
def cant_walk_through_solid_objects(event, _):
    event.cancel()


@Walk.check(DoorPhysics)
def cant_walk_through_closed_doors(event, door):
    if not IOpenable(door.entity).open:
        event.cancel()


@Walk.perform(Physics)
def do_walk(event, _):
    event.world.current_map.move(event.actor, event.target.position)


# -----------------------------------------------------------------------------
# Map portal

class IPortal(IComponent):
    destination = static_attribute("Name of the destination map.")


class Portal(Component, interface=IPortal):
    def __init__(self, *, destination):
        self.destination = destination


class PortalDownstairs(Portal):
    pass


@Descend.perform(PortalDownstairs)
def do_descend_stairs(event, portal):
    event.world.change_map(portal.destination)


class PortalUpstairs(Portal):
    pass


@Ascend.perform(PortalUpstairs)
def do_ascend_stairs(event, portal):
    event.world.change_map(portal.destination)


# -----------------------------------------------------------------------------
# Doors

class IOpenable(IComponent):
    open = static_attribute("""Whether I'm currently open.""")


class Openable(Component, interface=IOpenable):
    def __init__(self, *, open=False):
        self.open = open


# TODO maybe this merits a check rule?  maybe EVERYTHING does.
# TODO only if closed
@Open.perform(Openable)
def do_open(event, openable):
    openable.open = True


class ILockable(IComponent):
    locked = static_attribute("""Whether I'm currently locked.""")


class Lockable(Component, interface=ILockable):
    def __init__(self, *, locked=False):
        self.locked = locked


# TODO maybe this merits a check rule?  maybe EVERYTHING does.
# TODO only if closed
@Unlock.perform(Lockable)
def do_unlock(event, lockable):
    # TODO check that the key is a key, player holds it, etc.  (inform has
    # touchability rules for all this...)
    lockable.locked = False

    # Destroy the key.  TODO: need to be able to tell an entity that i'm taking
    # it away from whatever owns it, whatever that may mean!  inform's "now"
    # does this
    IContainer(event.actor).inventory.remove(event.agent)



@Open.check(Lockable)
def cant_open_locked_things(event, lockable):
    if lockable.locked:
        log.info("it's locked")
        event.cancel()


# -----------------------------------------------------------------------------
# Containment

class IContainer(IComponent):
    inventory = static_attribute("Items contained by this container.")


class Container(Component, interface=IContainer):
    # TODO surely this isn't called when something is polymorphed.  right?
    # or...  maybe it is, if the entity didn't have an IContainer before?
    def __init__(self):
        self.inventory = []


# -----------------------------------------------------------------------------
# Combat

class ICombatant(IComponent):
    """Implements an entity's ability to fight and take damage."""
    maximum_health = static_attribute("Entity's maximum possible health.")
    current_health = static_attribute("Current amount of health.")
    strength = static_attribute("Generic placeholder stat.")


class Combatant(Component, interface=ICombatant):
    """Regular creature that has stats, fights with weapons, etc."""
    def __typeinit__(self, *, health, strength):
        self.maximum_health = health
        self.current_health = health
        self.strength = strength

    # TODO need several things to happen with attributes here
    # 1. need to be able to pass them to Entity constructor
    # 2. not all attributes have or want a default
    # 3. some attributes are computed based on others
    # 4. some attributes want to be randomized in a range, i.e. need some sort
    # of constructor arguments that are used to compute an attribute but not
    # stored anywhere

    def lose_health(self, event):
        self.current_health -= event.amount

        # TODO i feel like this doesn't belong here (this definitely shouldn't
        # need to take an event object), but then where should it go?
        if self.current_health <= 0:
            event.world.queue_immediate_event(Die(self.entity))


@MeleeAttack.perform(Combatant)
def do_melee_attack(event, combatant):
    opponent = ICombatant(event.actor)
    event.world.queue_immediate_event(
        Damage(combatant.entity, opponent.strength))


@MeleeAttack.announce(Combatant)
def announce_melee_attack(event, combatant):
    log.info("{0} hits {1}".format(
        event.actor.type.name, combatant.entity.type.name))


@Damage.perform(Combatant)
def do_damage(event, combatant):
    combatant.lose_health(event)


@Die.perform(Combatant)
def do_die(event, combatant):
    # TODO player death is a little different...
    event.world.current_map.remove(combatant.entity)
    # TODO and drop inventory, and/or a corpse


@Die.announce(Combatant)
def announce_die(event, combatant):
    log.info("{} has died".format(combatant.entity.type.name))


class Breakable(Component, interface=ICombatant):
    def __typeinit__(self, *, health):
        self.maximum_health = health
        self.current_health = health
        # TODO breakables don't /have/ strength.  is this separate?
        # TODO should interfaces/components be able to say they can only exist
        # for entities that also support some other interface?
        self.strength = 0

    def __init__(self, health_fraction):
        self.current_health = health_fraction * self.maximum_health


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


class GenericAI(Component, interface=IActor):
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


class PlayerIntelligence(Component, interface=IActor):
    def act(self, world):
        if world.player_action_queue:
            world.queue_immediate_event(world.player_action_queue.popleft())


# -----------------------------------------------------------------------------
# Items

class IPortable(IComponent):
    """Entity can be picked up and placed in containers."""


class Portable(Component, interface=IPortable):
    pass


# TODO maybe "actor" could just be an event target, and we'd need fewer
# duplicate events for the source vs the target?
@PickUp.perform(Portable)
def do_pick_up(event, portable):
    from flax.entity import Layer
    assert portable.entity.type.layer is Layer.item
    event.world.current_map.remove(portable.entity)
    IContainer(event.actor).inventory.append(portable.entity)


@PickUp.announce(Portable)
def announce_pick_up(event, portable):
    log.info("ooh picking up {}".format(portable.entity.type.name))


# -----------------------------------------------------------------------------
# Equipment

class IBodied(IComponent):
    wearing = derived_attribute("")


# TODO this direly wants, like, a list of limbs and how many
class Bodied(Component, interface=IBodied):
    wearing = RelationSubject(Wearing)


class IEquipment(IComponent):
    # worn_by?
    modifiers = static_attribute("Stat modifiers granted by this equipment.")


class Equipment(Component, interface=IEquipment):
    # TODO i think this should live on Bodied as a simple dict of body part to
    # equipment
    # TODO problem is that if the player loses the item /for any reason
    # whatsoever/, the item needs to vanish from the dict.  ALSO, the existence
    # of the item in the dict can block some other actions.
    worn_by = RelationObject(Wearing)

    def __typeinit__(self, *, modifiers=None):
        self.modifiers = modifiers or ()

# TODO recurring problems with events:
# - what happens if something changes and the check is no
#   longer valid by the time the handler runs?  :S
# - similarly, what happens to events when an actor vanishes before
#   they get to fire?  that's an ongoing problem -- maybe should be
#   using weak properties for all the bound entities, and invalidating
#   the event when any entity vanishes
# TODO must be holding the armor...  or standing on it?


@Equip.check(Equipment)
def equipper_must_have_body_part(event, equipment):
    # TODO need to implement slots
    if IBodied not in event.actor:
        log.info("you can't wear that")
        event.cancel()


@Equip.check(Equipment)
def equipment_must_not_be_worn(event, equipment):
    if equipment.worn_by:
        log.info("that's already being worn")
        event.cancel()


@Equip.perform(Equipment)
def put_on_equipment(event, equipment):
    equipment.worn_by.add(event.actor)


@Equip.announce(Equipment)
def equipment_success(event, equipment):
    log.info("you put on the armor")


@Unequip.check(Equipment)
def can_only_equip_whats_equipped(event, equipment):
    if event.actor not in equipment.worn_by:
        log.info("you're not wearing the armor!")
        event.cancel()


@Unequip.perform(Equipment)
def take_off_equipment(event, equipment):
    self.worn_by.remove(event.actor)


@Unequip.announce(Equipment)
def unequip_success(event, equipment):
    log.info("you take off the armor")
