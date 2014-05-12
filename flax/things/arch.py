
class ThingType:
    pass

class CaveWall(ThingType):
    tmp_rendering = ' ', 'default'

class Wall(ThingType):
    tmp_rendering = 'X', 'default'

class Floor(ThingType):
    tmp_rendering = '·', 'floor'

class Player(ThingType):
    tmp_rendering = '☻', 'player'
