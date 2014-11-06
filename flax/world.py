from collections import deque

from flax.component import IActor, IPhysics, IOpenable
from flax.entity import Player
from flax.fractor import BinaryPartitionFractor
from flax.fractor import PerlinFractor
from flax.fractor import RuinFractor
from flax.fractor import RuinedHallFractor
from flax.geometry import Size


class FloorPlan:
    """Arrangement of the maps themselves."""
    # Will also take care of saving and loading later, maybe?
    def __init__(self, player):
        self.player = player

        # TODO just thinking about how this would work, for now
        #self.zones = {}
        #self.zones['kadath'] = [RuinLayout(), RuinLayout(), RuinLayout()]
        # TODO but really there should be a thing that generates a zone, too,
        # with its own handful of parameters.  also, "zone" is a bad name for a
        # region.

        # I suppose for now we'll just hardcode this, but...
        # TODO how will all this work?  where do the connections between maps
        # live?  do we decide the general structure (e.g. a split-off section
        # of the dungeon with X floors) and then tell the fractors to conform
        # to that?
        # TODO maybe maps should just know their own names
        # TODO check that all maps are connected?
        self.maps = {}
        self.maps['map0'] = RuinFractor(Size(120, 30)).generate_map(down='map1')
        self.maps['map1'] = RuinedHallFractor(Size(120, 30)).generate_map(up='map0', down='map2')
        self.maps['map2'] = PerlinFractor(Size(80, 24)).generate_map(up='map1', down='map3')
        self.maps['map3'] = BinaryPartitionFractor(Size(80, 24), minimum_size=Size(10, 8)).generate_map(up='map2')
        self.current_map_name = None
        self.current_map = None

        # TODO should this obj just switch to the first map when it starts?
        # that doesn't seem right.
        self.starting_map = 'map0'

    def change_map(self, new_map_name):
        # Probably should call world.change_map() instead, which will clear out
        # some map-specific state.
        new_map = self.maps[new_map_name]
        player_position = None

        if self.current_map:
            self.current_map.remove(self.player)

            dest_portal = new_map.portal_index.get(self.current_map_name)
            if dest_portal:
                player_position = new_map.find(dest_portal).position

        if player_position is None:
            # This shouldn't normally happen, but for the moment, it always
            # does when starting the game.  TODO should fractor do this?  not
            # terribly efficient atm  :)
            import random
            tiles = list(new_map.tiles.values())
            random.shuffle(tiles)
            while True:
                tile = tiles.pop(0)
                if not IPhysics(tile.architecture).blocks(self.player):
                    player_position = tile.position
                    break

        self.current_map_name = new_map_name
        self.current_map = new_map
        self.current_map.place(self.player, player_position)
        # TODO whoopsie, this doesn't actually update the map?


class World:
    """The world.  Contains the core implementations of event handling and
    player action handling.  Eventually will control loading/saving, generating
    new maps, inter-map movement, gameplay configuration, and the like.
    """
    def __init__(self):
        # There can only be one player object.  We own it.
        self.player = Player()

        self.player_action_queue = deque()
        self.event_queue = deque()

        self.floor_plan = FloorPlan(self.player)
        self.change_map(self.floor_plan.starting_map)

    @property
    def current_map(self):
        return self.floor_plan.current_map

    def change_map(self, map_name):
        # TODO refund time?  or only eat it after the events succeed
        self.event_queue.clear()

        self.floor_plan.change_map(map_name)

    def push_player_action(self, event):
        self.player_action_queue.append(event)

    def player_action_from_direction(self, direction):
        """Given a `Direction`, figure out what action the player probably
        intends to make in that direction.  i.e., if the space ahead of the
        player is empty, return `Walk`.
        """
        from flax.event import Walk, MeleeAttack, Open

        # TODO i sure do this a lot!  maybe write a method for it!
        new_pos = self.current_map.find(self.player).position + direction
        if new_pos not in self.current_map:
            return None
        tile = self.current_map.tiles[new_pos]

        if tile.creature:
            return MeleeAttack(self.player, direction)

        try:
            openable = IOpenable(tile.architecture)
        except KeyError:
            pass
        else:
            if not openable.open:
                return Open(self.player, tile.architecture)

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
