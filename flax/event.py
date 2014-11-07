from enum import Enum
import logging


log = logging.getLogger(__name__)


class EventListenerTarget(Enum):
    self = 'self'
    wearer = 'wearer'
    owner = 'owner'


class Rule:
    def __init__(self, function, direct_object, indirect_object=None):
        self.function = function
        self.direct_object = direct_object
        self.indirect_object = indirect_object


class Rulebook:
    def __init__(self):
        self.rules = []

    def __call__(self, *args, **kwargs):
        def decorator(f):
            self.add(Rule(f, *args, **kwargs))
            return f

        return decorator

    def add(self, rule):
        self.rules.append(rule)

    def run(self, subject, target):
        # TODO this knows a lot about events, whereas inform7 does not
        # TODO flesh this out, be less invasive
        for rule in self.rules:
            # TODO better "does this rule apply?" logic
            if rule.direct_object not in target:
                continue
            rule.function(subject, rule.direct_object.interface(target))


class CancelEvent(Exception):
    pass


class MetaEvent(type):
    def __init__(cls, name, bases, attrs):
        super().__init__(name, bases, attrs)
        cls.check = Rulebook()
        cls.perform = Rulebook()
        cls.announce = Rulebook()


# TODO is it worth separating "action" from "event"?  where an event is purely
# a side effect raised by a component that other stuff might want to respond
# to, e.g. /any/ destruction of an object should unequip it
# TODO probably want to convert all the existing events to use a standard
# subject, direct object, indirect object.  and maybe the direct object should
# never be a direction?
# TODO should a complete lack of applicable check rules count as a default
# failure?
# TODO it's not clear how effects /provided by/ equipment etc. would work with
# the rulebook approach
class Event(metaclass=MetaEvent):
    cancelled = False

    def fire(self, world):
        self.world = world

        if not self.target:
            log.debug("oops no target for {}".format(self))
            return

        try:
            multiplex_event = self.target.multiplex_event
        except AttributeError:
            targets = [self.target]
        else:
            targets = list(multiplex_event())

        # TODO is there any value in having separate perform and announce
        # stages?
        # TODO what if someone wants to pre-empt the normal perform?  do they
        # perform, announce, and then cancel?  so what's the point?
        try:
            for target in targets:
                # TODO self.target = target
                self.check.run(self, target)
            for target in targets:
                self.perform.run(self, target)
            for target in targets:
                self.announce.run(self, target)
        except CancelEvent:
            return

    def cancel(self):
        raise CancelEvent


class Walk(Event):
    def __init__(self, actor, direction):
        self.actor = actor
        self.direction = direction

    @property
    def target(self):
        map = self.world.current_map
        new_pos = map.find(self.actor).position + self.direction
        if new_pos not in map:
            # TODO complain?  or cancel?  or what?
            return None
        return map.tiles[new_pos]


class Descend(Event):
    def __init__(self, actor):
        self.actor = actor

    @property
    def target(self):
        map = self.world.current_map
        return map.find(self.actor)


class Ascend(Event):
    def __init__(self, actor):
        self.actor = actor

    @property
    def target(self):
        map = self.world.current_map
        return map.find(self.actor)


class Open(Event):
    def __init__(self, actor, target):
        self.actor = actor
        self.target = target

        # TODO complain unless actor is next to target?


class Unlock(Event):
    def __init__(self, actor, target, agent):
        self.actor = actor
        self.target = target
        self.agent = agent

        # TODO complain unless actor is next to target?


class PickUp(Event):
    def __init__(self, actor, item):
        self.actor = actor
        self.target = item

        # TODO complain unless actor is standing on item??


class Equip(Event):
    def __init__(self, actor, item):
        self.actor = actor
        self.target = item

        # TODO complain unless actor has or is standing on item??


class Unequip(Event):
    def __init__(self, actor, item):
        self.actor = actor
        self.target = item

        # TODO complain unless actor is wearing the item?



class MeleeAttack(Event):
    def __init__(self, actor, direction):
        # TODO a direction makes sense at a glance here since that's generally
        # how you swing e.g. a sword, but it won't work for throwing,
        # spellcasting, or any other kind of targeted thing, which may want to
        # share some of this code
        self.actor = actor
        self.direction = direction

    @property
    def target(self):
        map = self.world.current_map
        try:
            new_pos = map.find(self.actor).position + self.direction
        except KeyError:
            # TODO uggh this is also kind of a general problem: events queued
            # by entities who then die before they're fired.  i think i need
            # something like a queue where each item is tied to a weakref.
            # something similar would help with auto-discarding modifiers too
            return None
        if new_pos not in map:
            return None
        return map.tiles[new_pos].creature


class Damage(Event):
    cancelable = False

    def __init__(self, target, amount):
        self.actor = None  # TODO some kind of source?
        self.target = target
        self.amount = amount


class Die(Event):
    cancelable = False

    def __init__(self, target):
        self.target = target
