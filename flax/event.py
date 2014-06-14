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
        new_pos = map.find(self.actor) + self.direction
        return new_pos in map

    def find_targets(self, map):
        new_pos = map.find(self.actor) + self.direction
        tile = map.tiles[new_pos]
        return tile.things

    def default_behavior(self, map):
        new_pos = map.find(self.actor) + self.direction
        map.move(self.actor, new_pos)



