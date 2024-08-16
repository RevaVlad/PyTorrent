import socket
import pytest
import bitstring
import Message
import logging
from struct import pack, unpack
from peer import Peer


@pytest.fixture()
def peer():
    return Peer('127.0.0.1', 2)


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


