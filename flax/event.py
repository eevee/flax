class Event:
    cancelled = False

    def fire(self, map):
        if not self.is_valid(map):
            return

        for target in self.find_targets(map):
            target.handle_event(self)
            if self.cancelled:
                return

        self.default_behavior(map)

        # TODO bubble-out behavior too, so e.g. traps can respond /after/
        # success

    def cancel(self):
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
