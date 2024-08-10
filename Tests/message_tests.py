import logging

import bitstring
import pytest
import Message
from struct import pack


@pytest.fixture
def info_hash():
    return b'\x12\x34\x56\x78\x9A\xBC\xDE\xF0\x12\x34\x56\x78\x9A\xBC\xDE\xF0\x12\x34\x56\x78'


@pytest.fixture
def peer_id():
    return b'-AZ2060-6wfG2wk6wWLc'


@pytest.fixture
def block_index():
    return 26


@pytest.fixture
def segments():
    return bitstring.BitArray(bin='101010')


@pytest.fixture
def segments_to_bytes(segments):
    pieces_to_bytes = segments.tobytes()
    return pieces_to_bytes


class TestMessages:
    def test_handshake_encode(self, info_hash, peer_id):
        expected = pack(f'!B19s8s20s20s', 19, b'BitTorrent protocol', b'\x00' * 8, info_hash, peer_id)
        assert expected == Message.HandshakeMessage(info_hash, peer_id).encode()

    def test_handshake_decode(self, info_hash, peer_id):
        data = pack(f'!B19s8s20s20s', 19, b'BitTorrent protocol', b'\x00' * 8, info_hash, peer_id)
        expected = Message.HandshakeMessage.decode(data)
        assert expected.info_hash == info_hash and expected.peer_id == peer_id

    def test_interested_encode(self):
        expected = pack('!IB', 1, 2)
        assert expected == Message.InterestedMessage().encode()

    def test_interested_decode(self):
        data = pack('!IB', 1, 2)
        assert isinstance(Message.InterestedMessage.decode(data), Message.InterestedMessage)

    def test_interested_decode_incorrect(self, caplog):
        data = pack('!IB', 1, 0)
        with caplog.at_level(logging.ERROR):
            Message.InterestedMessage.decode(data)
            assert "получен некорректный индентификатор: 0" in caplog.text

    def test_unchoked_encode(self):
        expected = pack('!IB', 1, 1)
        assert expected == Message.UnChokedMessage().encode()

    def test_unchoked_decode(self):
        data = pack('!IB', 1, 1)
        assert isinstance(Message.UnChokedMessage.decode(data), Message.UnChokedMessage)

    def test_unchoked_decode_incorrect(self, caplog):
        data = pack('!IB', 1, 3)
        with caplog.at_level(logging.ERROR):
            Message.UnChokedMessage.decode(data)
            assert "получен некорректный индентификатор: 3" in caplog.text

    def test_peers_segments_encode(self, segments, segments_to_bytes):
        expected = pack(f'!IB{len(segments_to_bytes)}s', len(segments_to_bytes) + 1, 5, segments_to_bytes)
        assert expected == Message.PeerSegmentsMessage(segments).encode()

    def test_peers_segments_decode(self, segments, segments_to_bytes):
        data = pack(f'!IB{len(segments_to_bytes)}s', len(segments_to_bytes) + 1, 5, segments_to_bytes)
        decode_result = Message.PeerSegmentsMessage.decode(data)
        assert isinstance(decode_result, Message.PeerSegmentsMessage)
        assert decode_result.segments == segments.tobytes()





