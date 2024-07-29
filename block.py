class Block:
    Missing = 0
    Pending = 1
    Retrieved = 2

    def __init__(self, segment_id, offset, length=16384, rarity=0):
        self.segment_id = segment_id
        self.offset = offset
        self.length = length
        self.status = Block.Missing
        self.rarity = rarity
        self.data = None

    def update_rarity(self, new_value):
        self.rarity = new_value