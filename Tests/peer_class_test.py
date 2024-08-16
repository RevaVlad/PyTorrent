import socket
import pytest
import bitstring
import Message
import logging
from struct import pack
from pubsub import pub
from peer import Peer


@pytest.fixture()
def peer():
    return Peer('127.0.0.1', 2)


@pytest.fixture()
def info_hash():
    return b'\x12\x34\x56\x78\x9A\xBC\xDE\xF0\x12\x34\x56\x78\x9A\xBC\xDE\xF0\x12\x34\x56\x78'


@pytest.fixture()
def peer_id():
    return b'-AZ2060-6wfG2wk6wWLc'


@pytest.fixture
def messages():
    return [Message.ChokedMessage(), Message.UnChokedMessage(),
            Message.InterestedMessage(), Message.NotInterestedMessage(),
            Message.HaveMessage(5), Message.PeerSegmentsMessage(bitstring.BitArray(bin='101010')),
            Message.RequestsMessage(5, 1, 3), Message.SendPieceMessage(5, 1, b'Hi!'),
            Message.CancelMessage(5, 1, 3)]


@pytest.fixture(scope='class')
def mock_socket_class():
    class MockSocket:
        def __init__(self):
            self.messages = []

        def setblocking(self, flag):
            pass

        def send(self, message):
            self.messages.append(message)

    return MockSocket()


@pytest.fixture()
def mock_pubsub():
    class MockPubSub:
        def __init__(self):
            self.data = {}

        def update_part_bitfield(self, peer, piece):
            self.data['peer'] = peer
            self.data['piece_index'] = piece

        def update_all_bitfield(self, peer):
            self.data['peer'] = peer

        def send_piece(self, piece):
            self.data['piece_index'], self.data['byte_offset'], self.data['data'] = piece

        def request_piece(self, request, peer):
            self.data['peer'] = peer
            self.data['piece_index'], self.data['byte_offset'], self.data['block_len'] = request

    return MockPubSub()


class TestPeerClass:
    def test_analyze_message(self, messages):
        for message in messages:
            assert type(message) is type(Peer.analyze_message(message.encode()))

    def test_analyze_message_with_incorrect_message(self, caplog):
        with caplog.at_level(logging.ERROR):
            result = Peer.analyze_message(b'\x00\x01\x02\x03')
            assert result is None
            assert 'Некорректное сообщение, распаковка невозможна' in caplog.text

    def test_analyze_empty_message(self, caplog):
        with caplog.at_level(logging.ERROR):
            result = Peer.analyze_message(b'')
            assert result is None
            assert 'Некорректное сообщение, распаковка невозможна' in caplog.text

    def test_analyze_message_with_incorrect_message_index(self, caplog):
        with caplog.at_level(logging.ERROR):
            result = Peer.analyze_message(pack('!IB', 1, 20))
            assert result is None
            assert 'Некорректное сообщение, указан несуществующий id_message: 20' in caplog.text

    def test_connection(self, monkeypatch, peer, mock_socket_class):
        def mock_create_connection(address):
            return mock_socket_class

        with monkeypatch.context() as m:
            m.setattr(socket, 'create_connection', mock_create_connection)
            assert peer.connect() is True
            assert peer.is_active is True
            assert peer.socket is not None

    def test_connection_fail(self, monkeypatch, peer, caplog):
        def mock_connection_fail(address):
            raise socket.error()

        with caplog.at_level(logging.ERROR):
            with monkeypatch.context() as m:
                m.setattr(socket, 'create_connection', mock_connection_fail)
                assert peer.connect() is False
                assert peer.is_active is False
                assert peer.socket is None
                assert 'Socket error: Пир 127.0.0.1:6881 не может быть подключён' in caplog.text

    def test_send_message(self, monkeypatch, peer, mock_socket_class):
        peer.is_active = True
        with monkeypatch.context() as m:
            m.setattr(peer, 'socket', mock_socket_class)
            peer.send_message_to_peer(Message.SendPieceMessage(5, 1, b'Hi!').encode())
            assert peer.is_active is True
            assert Message.SendPieceMessage(5, 1, b'Hi!').encode() in mock_socket_class.messages

    def test_send_message_failed(self, monkeypatch, peer, caplog):
        class MockMessage:
            def send(self, message):
                raise socket.error()

        with caplog.at_level(logging.ERROR):
            with monkeypatch.context() as m:
                peer.is_active = True
                m.setattr(peer, 'socket', MockMessage())
                message = Message.SendPieceMessage(5, 1, b'Hi!').encode()
                peer.send_message_to_peer(message)
                assert peer.is_active is False
                assert f'Socket error. Невозможно отправить сообщение {message}'

    def test_properties(self, monkeypatch, peer, mock_socket_class):
        peer.peer_choked = False
        peer.interested = True
        peer.choked = False
        assert peer.peer_choked is False
        assert peer.interested is True
        assert peer.choked is False

        with monkeypatch.context() as m:
            peer.choked = True
            m.setattr(peer, 'socket', mock_socket_class)
            peer.peer_interested = True
            assert peer.peer_interested is True
            assert Message.UnChokedMessage().encode() in mock_socket_class.messages

    def test_available_pieces(self, peer):
        peer.bitfield = bitstring.BitArray(bin='10')
        assert peer.check_for_piece(0) == 1
        assert peer.check_for_piece(1) == 0

    def test_handle_got_piece(self, monkeypatch, peer, mock_socket_class, mock_pubsub):
        pub.subscribe(mock_pubsub.update_part_bitfield, 'updatePartBitfield')
        sent_peer = Peer('127.0.0.3', 2)
        with monkeypatch.context() as m:
            m.setattr(peer, 'socket', mock_socket_class)
            # Исправить когда появится класс Piece на какой-то piece вместо 1
            peer.handle_got_piece(sent_peer, 1)
            assert peer.interested is True
            assert Message.InterestedMessage().encode() in mock_socket_class.messages
            assert mock_pubsub.data['peer'].ip == sent_peer.ip and mock_pubsub.data['peer'].number_of_pieces == 2
            assert mock_pubsub.data['piece_index'] == 1

    def test_handle_available_piece(self, monkeypatch, peer, mock_socket_class, mock_pubsub):
        pub.subscribe(mock_pubsub.update_all_bitfield, 'updateAllBitfield')
        sent_peer = Peer('127.0.0.2', 2)
        sent_peer.bitfield = bitstring.BitArray(bin='10')
        peer.bitfield = bitstring.BitArray(bin='01')
        with monkeypatch.context() as m:
            m.setattr(peer, 'socket', mock_socket_class)
            peer.handle_available_piece(sent_peer)
            assert peer.interested is True
            assert Message.InterestedMessage().encode() in mock_socket_class.messages
            assert mock_pubsub.data['peer'].ip == sent_peer.ip and mock_pubsub.data['peer'].number_of_pieces == 2
            assert peer.bitfield == bitstring.BitArray(bin='11')

    def test_handle_send_piece(self, peer, mock_pubsub):
        pub.subscribe(mock_pubsub.send_piece, 'sendPiece')
        peer.handle_send_piece((1, 2, b'Hi'))
        assert mock_pubsub.data['piece_index'] == 1
        assert mock_pubsub.data['byte_offset'] == 2
        assert mock_pubsub.data['data'] == b'Hi'

    def test_handle_request(self, monkeypatch, peer, mock_socket_class, mock_pubsub):
        pub.subscribe(mock_pubsub.request_piece, 'requestPiece')
        with monkeypatch.context() as m:
            m.setattr(peer, 'socket', mock_socket_class)
            peer.peer_interested = True
            peer.peer_choked = False
            peer.handle_request((1, 2, 1))
            assert mock_pubsub.data['peer'].ip == '127.0.0.1' and mock_pubsub.data['peer'].number_of_pieces == 2
            assert mock_pubsub.data['piece_index'] == 1
            assert mock_pubsub.data['byte_offset'] == 2
            assert mock_pubsub.data['block_len'] == 1
            assert Message.UnChokedMessage().encode() in mock_socket_class.messages

    def test_handle_handshake(self, peer, info_hash, peer_id):
        peer.buffer = Message.HandshakeMessage(info_hash, peer_id).encode()
        assert peer.handle_handshake() is True
        assert peer.handshake is True
        assert peer.buffer == b''

    def test_handle_handshake_with_empty_peer_id(self, peer, info_hash):
        peer.buffer = Message.HandshakeMessage(info_hash).encode()
        assert peer.handle_handshake() is True
        assert peer.handshake is True
        assert peer.buffer == b''

    def test_handle_handshake_fail_incorrect_index(self, peer, info_hash, peer_id):
        peer.buffer = pack(f'!B19s8s20s20s', 32, b'BitTorrent protocol', b'\x00' * 8, info_hash, peer_id)
        assert peer.handle_handshake() is False
        assert peer.handshake is False

    def test_handle_handshake_fail_incorrect_data(self, peer, info_hash):
        peer.buffer = pack(f'!B19s8s20s20s', 32, b'BitTorrent protocol', b'\x00' * 8, info_hash, b'f3f4f')
        assert peer.handle_handshake() is False
        assert peer.handshake is False

    def test_continue_connection(self, peer):
        peer.buffer = Message.ContinueConnectionMessage().encode()
        assert peer.handle_continue_connection() is True
        assert peer.buffer == b''

    def test_continue_connection_fail_incorrect_data(self, peer):
        peer.buffer = pack('!I', 3)
        assert peer.handle_continue_connection() is False

    def test_get_message(self, peer):
        peer.is_active = True
        peer.handshake = True
        message = Message.InterestedMessage()
        peer.buffer = message.encode()

        result = list(peer.get_message())

        assert type(result[0]) is type(message)
        assert peer.buffer == b''

