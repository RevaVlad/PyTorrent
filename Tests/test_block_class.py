from block import Block
from unittest.mock import AsyncMock
import pytest
import logging
import asyncio


@pytest.fixture
def block():
    return Block(1, 0)


class TestBlockClass:
    def test_data_property_correct(self, block):
        block.data = b'1' * 214
        assert block.data == b'1' * 214

    def test_data_property_incorrect(self, block, caplog):
        with caplog.at_level(logging.ERROR):
            block.data = b'1'
            assert block.data is None
            assert f"Incorrect value for block: b'1'" in caplog.text
            caplog.clear()
            block.data = 'str'
            assert block.data is None
            assert f"Incorrect value for block: str" in caplog.text

    @pytest.mark.asyncio
    async def test_change_status_to_missing(self, block, monkeypatch):
        mock_sleep = AsyncMock()
        block.status = block.Pending
        with monkeypatch.context() as m:
            m.setattr(asyncio, 'sleep', mock_sleep)
            task = block.change_status_to_missing(2)
            await task
            mock_sleep.assert_called_once_with(2)
            assert block.status == Block.Missing

    @pytest.mark.asyncio
    async def test_not_change_status_to_missing(self, block, monkeypatch):
        mock_sleep = AsyncMock()
        block.status = block.Retrieved
        with monkeypatch.context() as m:
            m.setattr(asyncio, 'sleep', mock_sleep)
            task = block.change_status_to_missing(1)
            await task
            mock_sleep.assert_called_once_with(1)
            assert block.status == Block.Retrieved

    def test_hash(self, block):
        assert hash(block) == 12763

    def test_equal(self, block):
        block_2 = Block(1, 0)
        assert block == block_2

    @pytest.mark.asyncio
    async def test_close(self, block):
        block.close()
        assert block._status_update_task is None

        task = block.change_status_to_missing(3)
        await asyncio.sleep(0.1)
        assert not task.cancelled()

        block.close()
        await asyncio.sleep(0.1)
        assert task.cancelled()

