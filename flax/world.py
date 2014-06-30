from collections import deque

from flax.component import IActor
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
        # Perform a turn for every actor on the map
        # TODO this feels slightly laggier, i think, since the player's action
        # now happens kind of /whenever/.  might help to have a persistent list
        # of actors held by the map.  also to have a circular queue and just
        # wait when we get to the player and there's nothing to do.
        actors = []
        for tile in self.current_map.tiles.values():
            # TODO what if things other than creatures can think??  fuck
            if tile.creature:
                actors.append(tile.creature)

        # TODO should go in turn order
        for actor in actors:
            # TODO gross hack, that will hopefully just go away when this works
            # better  :(  if an earlier run of this loop caused an actor to no
            # longer be on the map, we shouldn't try to make it act
            if actor not in self.current_map.entity_positions:
                continue

            IActor(actor).act(self)
            self.drain_event_queue()

    def drain_event_queue(self):
        while self.event_queue:
            event = self.event_queue.popleft()
            event.fire(self)

    def queue_event(self, event):
        self.event_queue.append(event)

    def queue_immediate_event(self, event):
        self.event_queue.appendleft(event)
