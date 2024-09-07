import logging
import socket

import bitstring
import pytest
import Message
from struct import pack
from random import randint


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


@pytest.fixture
def index():
    return 52


@pytest.fixture
def byte_offset():
    return 5

@pytest.fixture
def sample_announce_response():
    action = 1
    transaction_id = 12345
    interval = 1800
    leechers = 50
    seeders = 100

    peer1_ip = socket.inet_aton('192.168.1.1')
    peer1_port = pack('!H', 6881)
    peer2_ip = socket.inet_aton('192.168.1.2')
    peer2_port = pack('!H', 6882)

    message = (
            pack('!I', action) +
            pack('!I', transaction_id) +
            pack('!I', interval) +
            pack('!I', leechers) +
            pack('!I', seeders) +
            peer1_ip + peer1_port +
            peer2_ip + peer2_port
    )

    return message


@pytest.fixture
def block():
    return b'Goodbye, Summer'


@pytest.fixture
def block_len(block):
    return len(block)


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
            assert 'При запросе на интерес был получен некорректный индентификатор: 0' in caplog.text

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
            assert 'При запросе на снятие заглушки был получен некорректный индентификатор: 3' in caplog.text

    def test_peers_segments_encode(self, segments, segments_to_bytes):
        expected = pack(f'!IB{len(segments_to_bytes)}s', len(segments_to_bytes) + 1, 5, segments_to_bytes)
        assert expected == Message.PeerSegmentsMessage(segments).encode()

    def test_peers_segments_decode(self, segments, segments_to_bytes):
        data = pack(f'!IB{len(segments_to_bytes)}s', len(segments_to_bytes) + 1, 5, segments_to_bytes)
        decode_result = Message.PeerSegmentsMessage.decode(data)
        assert isinstance(decode_result, Message.PeerSegmentsMessage)
        assert decode_result.segments == segments.tobytes()

    def test_request_message_encode(self, index, byte_offset, block_len):
        expected = pack(f'!IBIII', 13, 6, index, byte_offset, block_len)
        assert expected == Message.RequestsMessage(index, byte_offset, block_len).encode()

    def test_request_message_decode(self, index, byte_offset, block_len):
        data = pack(f'!IBIII', 13, 6, index, byte_offset, block_len)
        result = Message.RequestsMessage.decode(data)
        assert isinstance(result, Message.RequestsMessage)
        assert result.index == index
        assert result.byte_offset == byte_offset
        assert result.block_len == block_len

    def test_send_piece_message_encode(self, index, byte_offset, block):
        expected = pack(f'!IBII{len(block)}s', 9 + len(block), 7, index, byte_offset, block)
        assert expected == Message.SendPieceMessage(index, byte_offset, block).encode()

    def test_send_piece_message_decode(self, index, byte_offset, block):
        data = pack(f'!IBII{len(block)}s', 9 + len(block), 7, index, byte_offset, block)
        result = Message.SendPieceMessage.decode(data)
        assert isinstance(result, Message.SendPieceMessage)
        assert result.index == index
        assert result.byte_offset == byte_offset
        assert result.data == block

    def test_for_have_message_encode(self, index):
        expected = pack('!IBI', 5, 4, index)
        assert expected == Message.HaveMessage(index).encode()

    def test_for_have_message_decode(self, index):
        data = pack('!IBI', 5, 4, index)
        result = Message.HaveMessage.decode(data)
        assert isinstance(result, Message.HaveMessage)
        assert result.piece_index == index

    def test_for_cancel_message_encode(self, index, byte_offset, block_len):
        expected = pack('!IBIII', 13, 8, index, byte_offset, block_len)
        assert expected == Message.CancelMessage(index, byte_offset, block_len).encode()

    def test_for_cancel_message_decode(self, index, byte_offset, block_len):
        data = pack('!IBIII', 13, 8, index, byte_offset, block_len)
        result = Message.CancelMessage.decode(data)
        assert isinstance(result, Message.CancelMessage)
        assert result.piece_index == index
        assert result.byte_offset == byte_offset
        assert result.block_len == block_len

    def test_continue_connection_message_encode(self):
        expected = pack('!I', 0)
        assert expected == Message.ContinueConnectionMessage().encode()

    def test_continue_connection_message_decode(self):
        data = pack('!I', 0)
        result = Message.ContinueConnectionMessage.decode(data)
        assert isinstance(result, Message.ContinueConnectionMessage)

    def test_continue_connection_message_encode_incorrect(self, caplog):
        data = pack('!I', 3)
        with caplog.at_level(logging.ERROR):
            Message.ContinueConnectionMessage.decode(data)
            assert 'При попытке поддержания соединения было получено неккоректное сообщение: длина не нулевая' in caplog.text

    def test_choked_message_encode(self):
        expected = pack('!IB', 1, 0)
        assert expected == Message.ChokedMessage().encode()

    def test_choked_message_decode(self):
        data = pack('!IB', 1, 0)
        result = Message.ChokedMessage.decode(data)
        assert isinstance(result, Message.ChokedMessage)

    def test_choked_message_encode_incorrect(self, caplog):
        data = pack('!IB', 1, 3)
        with caplog.at_level(logging.ERROR):
            Message.ChokedMessage.decode(data)
            assert 'При запросе на включение заглушки был получен некорректный индентификатор: 3' in caplog.text

    def test_not_interested_message_encode(self):
        expected = pack('!IB', 1, 3)
        assert expected == Message.NotInterestedMessage().encode()

    def test_not_interested_message_decode(self):
        data = pack('!IB', 1, 3)
        result = Message.NotInterestedMessage.decode(data)
        assert isinstance(result, Message.NotInterestedMessage)

    def test_not_interested_message_encode_incorrect(self, caplog):
        data = pack('!IB', 1, 2)
        with caplog.at_level(logging.ERROR):
            Message.NotInterestedMessage.decode(data)
            assert 'При запросе на отсутсвие интереса был получен некорректный индентификатор: 2' in caplog.text

    def test_udp_connection_encode(self):
        message = Message.UDPConnectionMessage()
        assert message.encode() == pack('!Q', 0x41727101980) + pack('!I', 0) + pack('!I', message.transaction_id)

    def test_udp_connection_decode(self):
        message = Message.UDPConnectionMessage()
        trans_id = randint(0, 10 ** 5)
        message_output = pack('!IIQ', 0, trans_id, 0x41727101980)
        message.decode(message_output)
        assert message.transaction_id == trans_id
        assert 0 == message.action
        assert 0x41727101980 == message.connection_id

    def test_udp_announce_encode(self, info_hash, peer_id):
        message = Message.UPDTrackerAnnounceInput(info_hash, peer_id, 0x41727101980, 1)
        conn_id = pack('!Q', 0x41727101980)
        downloaded = pack('!Q', 0)
        left = pack('!Q', 0)
        uploaded = pack('!Q', 0)

        action = pack('!I', 1)
        trans_id = pack('!I', message.transaction_id)
        event = pack('!I', 1)
        ip = pack('!I', 0)
        key = pack('!I', 0)
        num_want = pack('!i', -1)
        port = pack('!h', 8000)
        assert (conn_id + action + trans_id + info_hash + peer_id + downloaded +
                left + uploaded + event + ip + key + num_want + port) == message.encode()

    def test_decode_announce_response(self, sample_announce_response):
        udp_output = Message.UPDTrackerAnnounceOutput()
        udp_output.decode(sample_announce_response)

        assert udp_output.action == 1
        assert udp_output.transaction_id == 12345
        assert udp_output.interval == 1800
        assert udp_output.leechers == 50
        assert udp_output.seeders == 100

        expected_peers = [
            ('192.168.1.1', 6881),
            ('192.168.1.2', 6882)
        ]
        assert udp_output.list_peers == expected_peers
