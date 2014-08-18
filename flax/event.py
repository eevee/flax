from enum import Enum


class EventListenerTarget(Enum):
    self = 'self'
    wearer = 'wearer'
    owner = 'owner'


# TODO a recurring theme in the other TODO's below is: where does "is this
# sane" belong?
class Event:
    cancelled = False

    def fire(self, world):
        self.world = world

        if not self.target:
            print("oops no target for", self)
            return

        self.target.handle_event(self)
        if self.cancelled:
            return

    def cancel(self):
        self.cancelled = True


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
