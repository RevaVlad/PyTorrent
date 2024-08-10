import logging

import pytest
import Message
from struct import pack


@pytest.fixture
def info_hash():
    return b'\x12\x34\x56\x78\x9A\xBC\xDE\xF0\x12\x34\x56\x78\x9A\xBC\xDE\xF0\x12\x34\x56\x78'


@pytest.fixture
def peer_id():
    return b'-AZ2060-6wfG2wk6wWLc'


class TestMessages:
    def test_handshake_encode(self, info_hash, peer_id):
        expected = pack(f'!B19s8s20s20s', 19, b'BitTorrent protocol', b'\x00' * 8, info_hash, peer_id)
        assert expected == Message.Handshake(info_hash, peer_id).encode()

    def test_handshake_decode(self, info_hash, peer_id):
        data = pack(f'!B19s8s20s20s', 19, b'BitTorrent protocol', b'\x00' * 8, info_hash, peer_id)
        expected = Message.Handshake.decode(data)
        assert expected.info_hash == info_hash and expected.peer_id == peer_id

    def test_interested_encode(self):
        expected = pack('!IB', 1, 2)
        assert expected == Message.Interested().encode()

    def test_interested_decode(self):
        data = pack('!IB', 1, 2)
        assert isinstance(Message.Interested.decode(data), Message.Interested)

    def test_interested_decode_incorrect(self, caplog):
        data = pack('!IB', 1, 0)
        with caplog.at_level(logging.ERROR):
            Message.Interested.decode(data)
            assert "получен некорректный индентификатор: 0" in caplog.text

    def test_unchoked_encode(self):
        expected = pack('!IB', 1, 1)
        assert expected == Message.UnChoked().encode()

    def test_unchoked_decode(self):
        data = pack('!IB', 1, 1)
        assert isinstance(Message.UnChoked.decode(data), Message.UnChoked)

    def test_unchoked_decode_incorrect(self, caplog):
        data = pack('!IB', 1, 3)
        with caplog.at_level(logging.ERROR):
            Message.UnChoked.decode(data)
            assert "получен некорректный индентификатор: 3" in caplog.text








