from collections import deque

from flax.fractor import generate_map


class World:
    """The world.  Contains the core implementations of event handling and
    player action handling.  Eventually will control loading/saving, generating
    new maps, inter-map movement, and the like.
    """
    def __init__(self):
        # TODO how to store the maps, to make looking through them a little
        # saner?
        self.maps = [generate_map()]
        self.current_map = self.maps[0]

        self.player_action_queue = deque()

    @property
    def player(self):
        return self.current_map.player

    def push_player_action(self, event):
        self.player_action_queue.append(event)

    def advance(self):
        # TODO this is all still bad for the same reasons as before: should
        # include the player in the loop somehow, should take time into account
        # for real
        if self.player_action_queue:
            player_action = self.player_action_queue.popleft()
            self.fire_event(player_action)

        # Perform a turn for everyone else
        from flax.things.arch import IActor
        actors = []
        for tile in self.current_map.tiles.values():
            # TODO what if things other than creatures can think??  fuck
            if tile.creature:
                actors.append(tile.creature)

        # TODO should go in turn order
        for actor in actors:
            action = IActor(actor).act()

            if action:
                self.fire_event(action)

    def fire_event(self, event):
        event.fire(self.current_map)
