from enum import Enum


class EventListenerTarget(Enum):
    self = 'self'
    wearer = 'wearer'
    owner = 'owner'


class Event:
    cancelled = False
    successful = False

    def fire(self, world, map):
        self.world = world

        if not self.target:
            print("oops no target for", self)
            return

        self.target.handle_event(self)
        if self.cancelled:
            return

        if not self.successful:
            pass
            # TODO is this...  bad?
            #print("WARNING: event didn't succeed", self)

    def cancel(self):
        assert not self.successful
        self.cancelled = True

    def succeed(self):
        assert not self.cancelled
        self.successful = True

    def find_target(self, map):
        raise NotImplementedError

    def default_behavior(self, map):
        raise NotImplementedError


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
        new_pos = map.find(self.actor).position + self.direction
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
