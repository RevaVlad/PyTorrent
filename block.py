class Block:
    BLOCK_LENGTH = 16384

    Missing = 0
    Pending = 1
    Retrieved = 2

    def __init__(self, segment_id, offset, length=BLOCK_LENGTH):
        self.segment_id = segment_id
        self.offset = offset
        self.length = length
        self.status = Block.Missing
        self.data = None
