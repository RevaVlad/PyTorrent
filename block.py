import asyncio
import logging


class Block:
    BLOCK_LENGTH = 214

    Missing = 0
    Pending = 1
    Retrieved = 2

    def __init__(self, segment_id, offset, length=BLOCK_LENGTH):
        self.segment_id = segment_id
        self.offset = offset
        self.length = length

        self.status = Block.Missing
        self._data = None

        self._status_update_task = None

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, value):
        if type(value) == bytes and len(value) == self.length:
            self._data = value
        else:
            logging.error(f"Incorrect value for block: {value}")

    def change_status_to_missing(self, delay=10):
        self._status_update_task = asyncio.create_task(self._change_status_to_missing_coroutine(delay))
        return self._status_update_task

    async def _change_status_to_missing_coroutine(self, delay):
        await asyncio.sleep(delay)
        if self.status == Block.Pending:
            self.status = Block.Missing

    def __hash__(self):
        return 12763 * self.segment_id + self.offset

    def __eq__(self, other):
        return type(other) == type(self) and self.segment_id == other.segment_id and self.offset == other.offset

    def close(self):
        if self._status_update_task:
            self._status_update_task.cancel()
