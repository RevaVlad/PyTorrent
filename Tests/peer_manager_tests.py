import pytest
import copy
import bitstring
import logging
import Message
import socket
import errno
from segment_downloader import SegmentDownloader
from peerconnection import PeerConnection
from pubsub import pub
from math import ceil


@pytest.fixture
def peer_manager():
    class TorrentData:
        def __init__(self, segment_length, total_length):
            self.info_hash = b'\x12\x34\x56\x78\x9A\xBC\xDE\xF0\x12\x34\x56\x78\x9A\xBC\xDE\xF0\x12\x34\x56\x78'
            self.segment_length = segment_length
            self.total_length = total_length
            self.total_segments = ceil(total_length / segment_length)

    peer = PeerConnection('127.0.0.1', 4)

    return SegmentDownloader(TorrentData(1, 4))


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


@pytest.fixture()
def peer():
    return PeerConnection('127.0.0.1', 4)



@pytest.fixture()
def peer_sent():
    return PeerConnection('127.0.0.4', 4)


@pytest.fixture()
def mock_pubsub():
    class MockPubSub:
        def __init__(self):
            self.data = {}

        def sub_to_request(self, request, peer):
            self.data['peer'] = peer
            self.data['request'] = request

        def sub_to_send(self, piece):
            self.data['piece'] = piece

    return MockPubSub()


class TestPeerManager:
    def test_request_piece_fail_request(self, caplog, peer_manager):
        with caplog.at_level(logging.ERROR):
            peer_manager.on_request_piece()
            assert 'Тело запроса пусто' in caplog.text

    def test_request_piece_fail_peer(self, caplog, peer_manager):
        with caplog.at_level(logging.ERROR):
            peer_manager.on_request_piece((1, 1, 2))
            assert 'Не указан пир, запросивший сегмент' in caplog.text

    def test_request_piece_succeed(self, monkeypatch, peer_manager, mock_socket_class, mock_segment_class):
        peer = PeerConnection('127.0.0.2', 4)
        with monkeypatch.context() as m:
            m.setattr(peer, 'socket', mock_socket_class)
            peer_manager.on_request_piece(mock_segment_class, peer)
            assert mock_socket_class.messages[0] == Message.SendPieceMessage(1, 1, b'need to update').encode()

    def test_update_all_bitfield_fail(self, peer_manager, caplog):
        with caplog.at_level(logging.ERROR):
            peer_manager.peers_bitfield_update_all()
            assert 'Не указан пир, у которого необходимо проверить наличие сегментов' in caplog.text

    def test_update_all_bitfield_succeed(self, peer_manager):
        peer = PeerConnection('127.0.0.2', 4)
        peer.bitfield = bitstring.BitArray(bin='1010')
        peer_manager.peers_bitfield_update_all(peer)
        for i in range(4):
            assert peer_manager.available_pieces[i][0] == (1 if i % 2 == 0 else 0)
            if i % 2 == 0:
                assert peer_manager.available_pieces[i][1][0].ip == '127.0.0.2'

    def test_update_all_bitfield_multiple_one_peer(self, peer_manager):
        peer = PeerConnection('127.0.0.2', 5)
        peer.bitfield = bitstring.BitArray(bin='1111')
        peer_manager.peers_bitfield_update_all(peer)
        peer_manager.peers_bitfield_update_all(peer)
        for i in range(4):
            assert peer_manager.available_pieces[i][0] == 1
            assert peer_manager.available_pieces[i][1][0].ip == '127.0.0.2'

    def test_update_all_bitfield_multiple(self, peer_manager):
        first_peer = PeerConnection('127.0.0.2', 4)
        first_peer.bitfield = bitstring.BitArray(bin='1100')
        peer_manager.peers_bitfield_update_all(first_peer)
        second_peer = PeerConnection('127.0.0.3', 4)
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
        peer = PeerConnection('127.0.0.2', 4)
        with caplog.at_level(logging.ERROR):
            peer_manager.peers_bitfield_update_piece(peer)
            assert 'Не указан индекс для отметки в bitField'

    def test_update_part_bitfield(self, peer_manager):
        peer = PeerConnection('127.0.0.2', 4)
        peer.bitfield = bitstring.BitArray(bin='0000')
        peer_manager.peers_bitfield_update_all(peer)
        peer.bitfield[0] = True
        peer_manager.peers_bitfield_update_piece(peer, 0)
        assert peer_manager.available_pieces[0][0] == 1
        assert peer_manager.available_pieces[0][1][0].ip == '127.0.0.2'

    def test_update_part_bitfield_multiple(self, peer_manager):
        first_peer = PeerConnection('127.0.0.2', 4)
        first_peer.bitfield = bitstring.BitArray(bin='1000')
        peer_manager.peers_bitfield_update_all(first_peer)
        second_peer = PeerConnection('127.0.0.3', 4)
        second_peer.bitfield = bitstring.BitArray(bin='1100')
        peer_manager.peers_bitfield_update_piece(second_peer, 0)
        peer_manager.peers_bitfield_update_piece(second_peer, 1)
        assert peer_manager.available_pieces[0][0] == 2
        assert peer_manager.available_pieces[0][1][0].ip == '127.0.0.2'
        assert peer_manager.available_pieces[0][1][1].ip == '127.0.0.3'
        assert peer_manager.available_pieces[1][0] == 1
        assert peer_manager.available_pieces[1][1][0].ip == '127.0.0.3'

    def test_peer_handshake_fail_peer(self, peer_manager, caplog):
        with caplog.at_level(logging.ERROR):
            result = peer_manager.peer_handshake()
            assert 'Не указан пир, которому нужно отправить handshake'
            assert result is False

    def test_peer_handshake_fail_error(self, monkeypatch, peer_manager, caplog, peer):
        class MockMessage:
            def send(self, message):
                raise socket.error()
        peer.is_active = True
        with caplog.at_level(logging.ERROR):
            with monkeypatch.context() as m:
                m.setattr(peer, 'socket', MockMessage())
                result = peer_manager.peer_handshake(peer)
                assert result is False
                assert 'Socket error. Невозможно отправить сообщение'
                assert 'Произошла ошибка при handshake-e, проверьте лог' in caplog.text

    def test_peer_handshake_succeed(self, monkeypatch, peer_manager, mock_socket_class):
        peer = PeerConnection('127.0.0.2', 4)
        peer.is_active = True
        with monkeypatch.context() as m:
            m.setattr(peer, 'socket', mock_socket_class)
            result = peer_manager.peer_handshake(peer)
            assert mock_socket_class.messages[0] == Message.HandshakeMessage(
                b'\x12\x34\x56\x78\x9A\xBC\xDE\xF0\x12\x34\x56\x78\x9A\xBC\xDE\xF0\x12\x34\x56\x78').encode()
            assert result is True

    def test_read_socket(self, monkeypatch, mock_socket_class):
        with monkeypatch.context() as m:
            mock_socket_class._set_recv_sequence([b'Hi', b'Bye', b''])
            m.setattr(socket.socket, 'recv', mock_socket_class.recv)
            result = SegmentDownloader.read_socket(socket.socket())
            assert result == b'HiBye'

    def test_read_socket_with_empty(self, monkeypatch, mock_socket_class):
        with monkeypatch.context() as m:
            mock_socket_class._set_recv_sequence([b''])
            m.setattr(socket.socket, 'recv', mock_socket_class.recv)
            result = SegmentDownloader.read_socket(socket.socket())
            assert result == b''

    def test_read_socket_fail_with_correct_errors(self, monkeypatch, caplog):
        def mock_fail_recv_eagain(self_imitation, buffer_size):
            raise socket.error(errno.EAGAIN, "EAGAIN error")

        def mock_fail_recv_ewouldblock(self_imitation, buffer_size):
            raise socket.error(errno.EWOULDBLOCK, "EAGAIN error")

        with caplog.at_level(logging.ERROR):
            with monkeypatch.context() as m:
                m.setattr(socket.socket, 'recv', mock_fail_recv_eagain)
                result = SegmentDownloader.read_socket(socket.socket())
                assert 'Произошла ошибка сокета' not in caplog.text
                assert result == b''

            with monkeypatch.context() as m:
                m.setattr(socket.socket, 'recv', mock_fail_recv_ewouldblock)
                result = SegmentDownloader.read_socket(socket.socket())
                assert 'Произошла ошибка сокета' not in caplog.text
                assert result == b''

    def test_read_socket_fail_incorrect_errors(self, monkeypatch, caplog):
        def mock_fail_recv(self_imitation, buffer_size):
            raise socket.error(errno.EBADF, "EBADF error")

        with caplog.at_level(logging.ERROR):
            with monkeypatch.context() as m:
                m.setattr(socket.socket, 'recv', mock_fail_recv)
                result = SegmentDownloader.read_socket(socket.socket())
                assert 'Произошла ошибка сокета: EBADF error' in caplog.text

    def test_get_new_message_with_handshake(self, peer_manager, caplog, peer):
        with caplog.at_level(logging.ERROR):
            peer_manager.get_new_message(Message.HandshakeMessage(b'\x12\x34\x56\x78\x9A\xBC\xDE\xF0\x12\x34\x56\x78\x9A\xBC\xDE\xF0\x12\x34\x56\x78'), peer)
            assert 'Обработка Handshake сообщения производится отедльно' in caplog.text

    def test_get_new_message_with_continue_connection(self, peer_manager, caplog, peer):
        with caplog.at_level(logging.ERROR):
            peer_manager.get_new_message(Message.ContinueConnectionMessage(), peer)
            assert 'Обработка ContinueConnection сообщения производится отедльно' in caplog.text

    def test_get_new_message_chocked(self, peer_manager, peer):
        peer.peer_choked = False
        peer_manager.get_new_message(Message.ChokedMessage(), peer)
        assert peer.peer_choked is True

    def test_get_new_message_unchoked(self, peer_manager, peer):
        peer_manager.get_new_message(Message.UnChokedMessage(), peer)
        assert peer.peer_choked is False

    def test_get_new_message_not_interested(self, peer_manager, peer):
        peer_manager.get_new_message(Message.NotInterestedMessage(), peer)
        assert peer.peer_interested is False

    def test_get_new_message_interested(self, monkeypatch, peer_manager, mock_socket_class, peer):
        with monkeypatch.context() as m:
            m.setattr(peer, 'socket', mock_socket_class)
            SegmentDownloader.get_new_message(Message.InterestedMessage(), peer)
            assert peer.peer_interested is True
            assert mock_socket_class.messages[0] == Message.UnChokedMessage().encode()

    def test_get_new_message_have(self, monkeypatch, mock_socket_class, peer_manager, peer_sent, peer):
        peer.bitfield = bitstring.BitArray(bin='0000')
        peer_sent.bitfield = bitstring.BitArray(bin='1000')
        message = Message.HaveMessage(0)
        with monkeypatch.context() as m:
            m.setattr(peer, 'socket', mock_socket_class)
            peer_manager.get_new_message(message, peer, peer_sent)
            assert peer.bitfield == bitstring.BitArray(bin='1000')
            assert peer_manager.available_pieces[0][0] == 1
            assert peer_manager.available_pieces[0][1][0].ip == '127.0.0.4'
            assert mock_socket_class.messages[0] == Message.InterestedMessage().encode()

    def test_get_new_message_send_available_pieces(self, monkeypatch, mock_socket_class, peer_manager, peer_sent, peer):
        peer.bitfield = bitstring.BitArray(bin='0100')
        peer_sent.bitfield = bitstring.BitArray(bin='1000')
        message = Message.PeerSegmentsMessage(peer_sent.bitfield)
        with monkeypatch.context() as m:
            m.setattr(peer, 'socket', mock_socket_class)
            peer_manager.get_new_message(message, peer, peer_sent)
            assert peer.bitfield == bitstring.BitArray(bin='1100')
            assert peer_manager.available_pieces[0][0] == 1
            assert peer_manager.available_pieces[0][1][0].ip == '127.0.0.4'
            assert mock_socket_class.messages[0] == Message.InterestedMessage().encode()

    def test_get_new_message_request(self, monkeypatch, peer_manager, mock_socket_class, mock_pubsub, peer):
        message = Message.RequestsMessage(1, 1, 4)
        pub.subscribe(mock_pubsub.sub_to_request, 'requestPiece')
        with monkeypatch.context() as m:
            m.setattr(peer, 'socket', mock_socket_class)
            peer.peer_choked = False
            peer.peer_interested = True
            assert mock_socket_class.messages[0] == Message.UnChokedMessage().encode()
            peer_manager.get_new_message(message, peer)
            assert mock_pubsub.data['peer'].ip == '127.0.0.1'
            assert mock_pubsub.data['request'].encode() == message.encode()

    def test_get_message_send_piece(self, peer_manager, mock_pubsub, peer):
        message = Message.SendPieceMessage(1, 1, b'Hi')
        pub.subscribe(mock_pubsub.sub_to_send, 'sendPiece')
        peer_manager.get_new_message(message, peer)
        assert mock_pubsub.data['piece'].encode() == message.encode()

    def test_get_message_cancel(self, peer_manager, caplog, peer):
        with caplog.at_level(logging.INFO):
            message = Message.CancelMessage(1, 1, 4)
            peer_manager.get_new_message(message, peer)
            assert 'CancelMessage' in caplog.text

    def test_get_message_fail(self, caplog, peer_manager, peer):
        class IncorrectMessage(Message.Message):
            def encode(self):
                pass

            @staticmethod
            def decode(data):
                pass

        with caplog.at_level(logging.ERROR):
            message = IncorrectMessage()
            peer_manager.get_new_message(message, peer)
            assert 'Такого типа сообщения нет' in caplog.text
