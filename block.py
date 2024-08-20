import asyncio
import logging


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
        self._data = None

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, value):
        if type(value) == bytes and len(value) == self.length:
            self._data = value
        else:
            logging.error(f"Incorrect value for block: {value}")

    async def change_status_to_missing(self, delay=10):
        await asyncio.sleep(delay)
        self.status = Block.Missing

    def __hash__(self):
        return 12763 * self.segment_id + self.offset

    def __eq__(self, other):
        return type(other) == type(self) and self.segment_id == other.segment_id and self.offset == other.offset
