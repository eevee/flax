from enum import Enum


class EventListenerTarget(Enum):
    self = 'self'
    wearer = 'wearer'
    owner = 'owner'


class Event:
    cancelable = True
    cancelled = False

    def fire(self, world, map):
        self.world = world

        if not self.is_valid(map):
            return

        for target in self.find_targets(map):
            target.handle_event(self)
            if self.cancelled:
                return

        self.default_behavior(map)

    def cancel(self):
        assert self.cancelable
        self.cancelled = True

    def is_valid(self, map):
        return True

    def find_target(self, map):
        raise NotImplementedError

    def default_behavior(self, map):
        raise NotImplementedError


class Walk(Event):
    def __init__(self, actor, direction):
        self.actor = actor
        self.direction = direction

    def is_valid(self, map):
        # TODO there sure is a lot of duplicated stuff here; should the event
        # constructor just take a map/world?
        new_pos = map.find(self.actor) + self.direction
        return new_pos in map

    def find_targets(self, map):
        new_pos = map.find(self.actor) + self.direction
        tile = map.tiles[new_pos]
        return tile.things

    def default_behavior(self, map):
        new_pos = map.find(self.actor) + self.direction
        map.move(self.actor, new_pos)


class MeleeAttack(Event):
    def __init__(self, actor, direction):
        # TODO a direction makes sense at a glance here since that's generally
        # how you swing e.g. a sword, but it won't work for throwing,
        # spellcasting, or any other kind of targeted thing, which may want to
        # share some of this code
        self.actor = actor
        self.direction = direction

    def is_valid(self, map):
        # TODO copy/pasted from above
        new_pos = map.find(self.actor) + self.direction
        return new_pos in map

    def find_targets(self, map):
        new_pos = map.find(self.actor) + self.direction
        tile = map.tiles[new_pos]
        if tile.creature:
            return [tile.creature]
        else:
            # TODO this should probably fire a message?
            return []

    def default_behavior(self, map):
        print("{0} hits {1}".format(self.actor, self.find_targets(map)))

        # TODO yeahhh uh this should probably like.  not need to be called
        # twice?  maybe pass them in?
        for target in self.find_targets(map):
            # TODO what's the amount
            self.world.queue_immediate_event(Damage(target, 5))


class Damage(Event):
    cancelable = False

    def __init__(self, target, amount):
        self.target = target
        self.amount = amount

    def find_targets(self, map):
        return [self.target]

    def default_behavior(self, map):
        from flax.things.arch import ICombatant
        ICombatant(self.target).damage(self.amount)

        # XXX this should really be in damage() but there's no access to the
        # world from there
        if ICombatant(self.target).health <= 0:
            self.world.queue_immediate_event(Die(self.target))


class Die(Event):
    cancelable = False

    def __init__(self, target):
        self.target = target

    def find_targets(self, map):
        return [self.target]

    def default_behavior(self, map):
        # TODO player death is different; probably raise an exception
        print("{} has died".format(self.target))
        map.remove(self.target)
        # TODO and drop inventory, and/or a corpse
