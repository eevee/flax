from collections import deque

from flax.fractor import generate_map


class World:
    """The world.  Contains the core implementations of event handling and
    player action handling.  Eventually will control loading/saving, generating
    new maps, inter-map movement, gameplay configuration, and the like.
    """
    def __init__(self):
        # TODO how to store the maps, to make looking through them a little
        # saner?
        self.maps = [generate_map()]
        self.current_map = self.maps[0]

        self.player_action_queue = deque()
        self.event_queue = deque()

    @property
    def player(self):
        return self.current_map.player

    def push_player_action(self, event):
        self.player_action_queue.append(event)

    def player_action_from_direction(self, direction):
        """Given a `Direction`, figure out what action the player probably
        intends to make in that direction.  i.e., if the space ahead of the
        player is empty, return `Walk`.
        """
        from flax.event import Walk, MeleeAttack

        # TODO i sure do this a lot!  maybe write a method for it!
        new_pos = self.current_map.find(self.player).position + direction
        if new_pos not in self.current_map:
            return None
        tile = self.current_map.tiles[new_pos]

        if tile.creature:
            return MeleeAttack(self.player, direction)
        else:
            return Walk(self.player, direction)

    def advance(self):
        # TODO this is all still bad for the same reasons as before: should
        # include the player in the loop somehow, should take time into account
        # for real
        if self.player_action_queue:
            player_action = self.player_action_queue.popleft()
            self.queue_event(player_action)
            self.drain_event_queue()

        # Perform a turn for everyone else
        from flax.things.arch import IActor
        actors = []
        for tile in self.current_map.tiles.values():
            # TODO what if things other than creatures can think??  fuck
            if tile.creature:
                actors.append(tile.creature)

        # TODO should go in turn order
        for actor in actors:
            IActor(actor).act(self)
            self.drain_event_queue()

    def drain_event_queue(self):
        while self.event_queue:
            event = self.event_queue.popleft()
            event.fire(self, self.current_map)

    def queue_event(self, event):
        self.event_queue.append(event)

    def queue_immediate_event(self, event):
        self.event_queue.appendleft(event)
