import pytest
import copy
import bitstring
import logging
import Message
import socket
import errno
from peer_manager import PeerManager
from peer import Peer
from math import ceil


@pytest.fixture
def peer_manager():
    class TorrentData:
        def __init__(self, segment_length, total_length):
            self.info_hash = b'\x12\x34\x56\x78\x9A\xBC\xDE\xF0\x12\x34\x56\x78\x9A\xBC\xDE\xF0\x12\x34\x56\x78'
            self.segment_length = segment_length
            self.total_length = total_length
            self.total_segments = ceil(total_length / segment_length)

    peer = Peer('127.0.0.1', 4)

    return PeerManager(peer, TorrentData(1, 4))


@pytest.fixture()
def mock_socket_class():
    class MockSocket:
        def __init__(self):
            self.messages = []
            self.recv_sequence = []

        def setblocking(self, flag):
            pass

        def send(self, message):
            self.messages.append(message)

        def recv(self, buffer_size):
            if self.recv_sequence:
                return self.recv_sequence.pop(0)
            return b''

        def _set_recv_sequence(self, sequence):
            self.recv_sequence = copy.copy(sequence)

    return MockSocket()


@pytest.fixture()
def mock_segment_class():
    class MockSegment:
        def __init__(self):
            self.index = 1
            self.byte_offset = 1
            self.block_length = 14

    return MockSegment()


class TestPeerManager:
    def test_request_piece_fail_request(self, caplog, peer_manager):
        with caplog.at_level(logging.ERROR):
            peer_manager.request_piece()
            assert 'Тело запроса пусто' in caplog.text

    def test_request_piece_fail_peer(self, caplog, peer_manager):
        with caplog.at_level(logging.ERROR):
            peer_manager.request_piece((1, 1, 2))
            assert 'Не указан пир, запросивший сегмент' in caplog.text

    def test_request_piece_succeed(self, monkeypatch, peer_manager, mock_socket_class, mock_segment_class):
        peer = Peer('127.0.0.2', 4)
        with monkeypatch.context() as m:
            m.setattr(peer, 'socket', mock_socket_class)
            peer_manager.request_piece(mock_segment_class, peer)
            assert mock_socket_class.messages[0] == Message.SendPieceMessage(1, 1, b'need to update').encode()

    def test_update_all_bitfield_fail(self, peer_manager, caplog):
        with caplog.at_level(logging.ERROR):
            peer_manager.peers_bitfield_update_all()
            assert 'Не указан пир, у которого необходимо проверить наличие сегментов' in caplog.text

    def test_update_all_bitfield_succeed(self, peer_manager):
        peer = Peer('127.0.0.2', 4)
        peer.bitfield = bitstring.BitArray(bin='1010')
        peer_manager.peers_bitfield_update_all(peer)
        for i in range(4):
            assert peer_manager.available_pieces[i][0] == (1 if i % 2 == 0 else 0)
            if i % 2 == 0:
                assert peer_manager.available_pieces[i][1][0].ip == '127.0.0.2'

    def test_update_all_bitfield_multiple_one_peer(self, peer_manager):
        peer = Peer('127.0.0.2', 5)
        peer.bitfield = bitstring.BitArray(bin='1111')
        peer_manager.peers_bitfield_update_all(peer)
        peer_manager.peers_bitfield_update_all(peer)
        for i in range(4):
            assert peer_manager.available_pieces[i][0] == 1
            assert peer_manager.available_pieces[i][1][0].ip == '127.0.0.2'

    def test_update_all_bitfield_multiple(self, peer_manager):
        first_peer = Peer('127.0.0.2', 4)
        first_peer.bitfield = bitstring.BitArray(bin='1100')
        peer_manager.peers_bitfield_update_all(first_peer)
        second_peer = Peer('127.0.0.3', 4)
        second_peer.bitfield = bitstring.BitArray(bin='0110')
        peer_manager.peers_bitfield_update_all(second_peer)
        assert peer_manager.available_pieces[0][0] == 1 and peer_manager.available_pieces[0][1][0].ip == '127.0.0.2'
        assert peer_manager.available_pieces[1][0] == 2
        assert peer_manager.available_pieces[1][1][0].ip == '127.0.0.2'
        assert peer_manager.available_pieces[1][1][1].ip == '127.0.0.3'
        assert peer_manager.available_pieces[2][0] == 1 and peer_manager.available_pieces[2][1][0].ip == '127.0.0.3'
        assert peer_manager.available_pieces[3][0] == 0 and len(peer_manager.available_pieces[3][1]) == 0

    def test_update_part_bitfield_fail_peer(self, peer_manager, caplog):
        with caplog.at_level(logging.ERROR):
            peer_manager.peers_bitfield_update_piece()
            assert 'Не указан пир, у которого есть сегмент'

    def test_update_part_bitfield_fail_piece(self, peer_manager, caplog):
        peer = Peer('127.0.0.2', 4)
        with caplog.at_level(logging.ERROR):
            peer_manager.peers_bitfield_update_piece(peer)
            assert 'Не указан индекс для отметки в bitField'

    def test_update_part_bitfield(self, peer_manager):
        peer = Peer('127.0.0.2', 4)
        peer.bitfield = bitstring.BitArray(bin='0000')
        peer_manager.peers_bitfield_update_all(peer)
        peer.bitfield[0] = True
        peer_manager.peers_bitfield_update_piece(peer, 0)
        assert peer_manager.available_pieces[0][0] == 1
        assert peer_manager.available_pieces[0][1][0].ip == '127.0.0.2'

    def test_update_part_bitfield_multiple(self, peer_manager):
        first_peer = Peer('127.0.0.2', 4)
        first_peer.bitfield = bitstring.BitArray(bin='1000')
        peer_manager.peers_bitfield_update_all(first_peer)
        second_peer = Peer('127.0.0.3', 4)
        second_peer.bitfield = bitstring.BitArray(bin='1100')
        peer_manager.peers_bitfield_update_piece(second_peer, 0)
        peer_manager.peers_bitfield_update_piece(second_peer, 1)
        assert peer_manager.available_pieces[0][0] == 2
        assert peer_manager.available_pieces[0][1][0].ip == '127.0.0.2'
        assert peer_manager.available_pieces[0][1][1].ip == '127.0.0.3'
        assert peer_manager.available_pieces[1][0] == 1
        assert peer_manager.available_pieces[1][1][0].ip == '127.0.0.3'

    def test_peer_handshake_fail(self, peer_manager, caplog):
        with caplog.at_level(logging.ERROR):
            peer_manager.peer_handshake()
            assert 'Не указан пир, которому нужно отправить handshake'

    def test_peer_handshake_succeed(self, monkeypatch, peer_manager, mock_socket_class):
        peer = Peer('127.0.0.2', 4)
        with monkeypatch.context() as m:
            m.setattr(peer, 'socket', mock_socket_class)
            peer_manager.peer_handshake(peer)
            assert mock_socket_class.messages[0] == Message.HandshakeMessage(
                b'\x12\x34\x56\x78\x9A\xBC\xDE\xF0\x12\x34\x56\x78\x9A\xBC\xDE\xF0\x12\x34\x56\x78').encode()

    def test_read_socket(self, monkeypatch, mock_socket_class):
        with monkeypatch.context() as m:
            mock_socket_class._set_recv_sequence([b'Hi', b'Bye', b''])
            m.setattr(socket.socket, 'recv', mock_socket_class.recv)
            result = PeerManager.read_socket(socket.socket())
            assert result == b'HiBye'

    def test_read_socket_with_empty(self, monkeypatch, mock_socket_class):
        with monkeypatch.context() as m:
            mock_socket_class._set_recv_sequence([b''])
            m.setattr(socket.socket, 'recv', mock_socket_class.recv)
            result = PeerManager.read_socket(socket.socket())
            assert result == b''

    def test_read_socket_fail_with_correct_errors(self, monkeypatch, caplog):
        def mock_fail_recv_eagain(self_imitation, buffer_size):
            raise socket.error(errno.EAGAIN, "EAGAIN error")

        def mock_fail_recv_ewouldblock(self_imitation, buffer_size):
            raise socket.error(errno.EWOULDBLOCK, "EAGAIN error")

        with caplog.at_level(logging.ERROR):
            with monkeypatch.context() as m:
                m.setattr(socket.socket, 'recv', mock_fail_recv_eagain)
                result = PeerManager.read_socket(socket.socket())
                assert 'Произошла ошибка сокета' not in caplog.text
                assert result == b''

            with monkeypatch.context() as m:
                m.setattr(socket.socket, 'recv', mock_fail_recv_ewouldblock)
                result = PeerManager.read_socket(socket.socket())
                assert 'Произошла ошибка сокета' not in caplog.text
                assert result == b''

    def test_read_socket_fail_incorrect_errors(self, monkeypatch, caplog):
        def mock_fail_recv(self_imitation, buffer_size):
            raise socket.error(errno.EBADF, "EBADF error")

        with caplog.at_level(logging.ERROR):
            with monkeypatch.context() as m:
                m.setattr(socket.socket, 'recv', mock_fail_recv)
                result = PeerManager.read_socket(socket.socket())
                assert 'Произошла ошибка сокета: EBADF error' in caplog.text
