import asyncio
import pytest
import bitstring
import Message
import logging
from unittest.mock import AsyncMock
from struct import pack
from pubsub import pub
from peer_connection import PeerConnection


@pytest.fixture()
def info_hash():
    return b'\x12\x34\x56\x78\x9A\xBC\xDE\xF0\x12\x34\x56\x78\x9A\xBC\xDE\xF0\x12\x34\x56\x78'


@pytest.fixture()
def peer(info_hash):
    return PeerConnection('127.0.0.1', 2, info_hash)


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


class TestPeerClass:
    def test_analyze_message(self, messages):
        for message in messages:
            assert type(message) is type(PeerConnection.analyze_message(message.encode()))

    def test_analyze_message_with_incorrect_message(self, caplog):
        with caplog.at_level(logging.ERROR):
            result = PeerConnection.analyze_message(b'\x00\x01\x02\x03')
            assert result is None
            assert 'Некорректное сообщение, распаковка невозможна' in caplog.text

    def test_analyze_empty_message(self, caplog):
        with caplog.at_level(logging.ERROR):
            result = PeerConnection.analyze_message(b'')
            assert result is None
            assert 'Некорректное сообщение, распаковка невозможна' in caplog.text

    def test_analyze_message_with_incorrect_message_index(self, caplog):
        with caplog.at_level(logging.ERROR):
            result = PeerConnection.analyze_message(pack('!IB', 1, 20))
            assert result is None
            assert 'Некорректное сообщение, указан несуществующий id_message: 20' in caplog.text

    @pytest.mark.asyncio
    async def test_connect_success(self, monkeypatch, info_hash):
        mock_open_connection = AsyncMock(return_value=(AsyncMock(), AsyncMock()))
        monkeypatch.setattr(asyncio, 'open_connection', mock_open_connection)

        peer = PeerConnection('127.0.0.1', 6881, info_hash)
        result = await peer.connect()

        assert result is True
        assert peer.is_active is True
        mock_open_connection.assert_called_once_with('127.0.0.1', 6881)

    @pytest.mark.asyncio
    async def test_connect_timeout_error(self, monkeypatch, caplog, info_hash, peer):
        mock_open_connection = AsyncMock(side_effect=asyncio.TimeoutError)
        monkeypatch.setattr(asyncio, 'open_connection', mock_open_connection)

        with caplog.at_level(logging.ERROR):
            result = await peer.connect()

        assert result is False
        assert peer.is_active is False
        assert "Socket error" in caplog.text
        mock_open_connection.assert_called_once_with('127.0.0.1', 6881)

    @pytest.mark.asyncio
    async def test_connect_os_error(self, monkeypatch, caplog, info_hash, peer):
        mock_open_connection = AsyncMock(side_effect=OSError)
        monkeypatch.setattr(asyncio, 'open_connection', mock_open_connection)

        with caplog.at_level(logging.ERROR):
            result = await peer.connect()

        assert result is False
        assert peer.is_active is False
        assert "Socket error" in caplog.text
        mock_open_connection.assert_called_once_with('127.0.0.1', 6881)

    @pytest.mark.asyncio
    async def test_send_message(self, monkeypatch, peer):
        peer.is_active = True
        peer.handshake = True
        mock_writer = AsyncMock()
        with monkeypatch.context() as m:
            m.setattr(peer, 'writer', mock_writer)
            result = await peer.send_message_to_peer(Message.HaveMessage(1))
            assert peer.is_active is True
            assert result is True
            mock_writer.write.assert_called_once_with(Message.HaveMessage(1).encode())
            mock_writer.drain.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_failed_no_handshake(self, monkeypatch, peer, caplog):
        peer.is_active = True
        mock_writer = AsyncMock()
        with monkeypatch.context() as m:
            m.setattr(peer, 'writer', mock_writer)
            result = await peer.send_message_to_peer(Message.RequestsMessage(5, 1, 3))
            assert result is False
            mock_writer.write.assert_not_called()
            mock_writer.drain.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_message_failed_error(self, monkeypatch, peer, caplog):
        peer.is_active = True
        peer.handshake = True
        writer = AsyncMock()
        writer.drain.side_effect = OSError
        with caplog.at_level(logging.ERROR):
            with monkeypatch.context() as m:
                m.setattr(peer, 'writer', writer)
                result = await peer.send_message_to_peer(Message.RequestsMessage(5, 1, 3))
            assert peer.is_active is False
            assert result is False

    @pytest.mark.asyncio
    async def test_properties(self, monkeypatch, peer):
        peer.peer_choked = False
        peer.interested = True
        peer.choked = False
        assert peer.peer_choked is False
        assert peer.interested is True
        assert peer.choked is False

        mock_send = AsyncMock()
        with monkeypatch.context() as m:
            peer.choked = True
            m.setattr(peer, 'send_message_to_peer', mock_send)
            peer.peer_interested = True
            assert peer.peer_interested is True

    def test_available_pieces(self, peer):
        peer.bitfield = bitstring.BitArray(bin='10')
        assert peer.check_for_piece(0) == 1
        assert peer.check_for_piece(1) == 0

    @pytest.mark.asyncio
    async def test_handle_got_piece(self, monkeypatch, peer):
        with monkeypatch.context() as m:
            mock_pubsub = AsyncMock()
            m.setattr(pub, 'sendMessage', mock_pubsub)
            mock_send = AsyncMock()
            m.setattr(peer, 'send_message_to_peer', mock_send)
            message = Message.HaveMessage(1)
            await peer.handle_got_piece(message)
        assert peer.bitfield[1] is True
        assert peer.interested is True
        mock_pubsub.assert_called_once_with(
            peer.have_message_event,
            index=1,
            peer=peer
        )

        assert mock_send.call_count == 1
        assert isinstance(mock_send.call_args[0][0], Message.InterestedMessage)

    @pytest.mark.asyncio
    async def test_handle_available_piece(self, monkeypatch, peer):
        peer.bitfield = bitstring.BitArray(bin='00')
        with monkeypatch.context() as m:
            mock_pubsub = AsyncMock()
            m.setattr(pub, 'sendMessage', mock_pubsub)
            mock_send = AsyncMock()
            m.setattr(peer, 'send_message_to_peer', mock_send)
            message = Message.PeerSegmentsMessage(bitstring.BitArray(bin='10'))
            await peer.handle_available_piece(message)
        assert peer.interested is True
        assert peer.bitfield == bitstring.BitArray(bin='10')
        mock_pubsub.assert_called_once_with(
            peer.bitfield_update_event,
            peer=peer
        )
        assert mock_send.call_count == 1
        assert isinstance(mock_send.call_args[0][0], Message.InterestedMessage)

    def test_handle_send_piece(self, peer, monkeypatch):
        mock_pubsub = AsyncMock()
        with monkeypatch.context() as m:
            m.setattr(pub, 'sendMessage', mock_pubsub)
            message = Message.SendPieceMessage(1, 1, b'Hi')
            peer.handle_piece_receive(message)
        mock_pubsub.assert_called_once_with(
            peer.receive_event,
            request=message,
            peer=peer
        )

    @pytest.mark.asyncio
    async def test_handle_request(self, monkeypatch, peer):
        peer.peer_choked = False
        mock_pubsub = AsyncMock()
        with monkeypatch.context() as m:
            m.setattr(pub, 'sendMessage', mock_pubsub)
            mock_send = AsyncMock()
            m.setattr(peer, 'send_message_to_peer', mock_send)
            peer.peer_interested = True
            message = Message.RequestsMessage(5, 1, 10)
            peer.handle_piece_request(message)
        mock_pubsub.assert_called_once_with(
            peer.request_event,
            request=message,
            peer=peer
        )

    def test_handle_handshake_buffer(self, peer, info_hash, peer_id):
        peer.buffer = Message.HandshakeMessage(info_hash, peer_id).encode()
        assert peer.handle_handshake_for_buffer() is True
        assert peer.handshake is True
        assert peer.buffer == b''

    def test_handle_handshake_buffer_with_empty_peer_id(self, peer, info_hash):
        peer.buffer = Message.HandshakeMessage(info_hash).encode()
        assert peer.handle_handshake_for_buffer() is True
        assert peer.handshake is True
        assert peer.buffer == b''

    def test_handle_handshake_buffer_fail_incorrect_index(self, peer, info_hash, peer_id):
        peer.buffer = pack(f'!B19s8s20s20s', 32, b'BitTorrent protocol', b'\x00' * 8, info_hash, peer_id)
        assert peer.handle_handshake_for_buffer() is False
        assert peer.handshake is False

    def test_handle_handshake_buffer_fail_incorrect_data(self, peer, info_hash):
        peer.buffer = pack(f'!B19s8s20s20s', 32, b'BitTorrent protocol', b'\x00' * 8, info_hash, b'f3f4f')
        assert peer.handle_handshake_for_buffer() is False
        assert peer.handshake is False

    def test_continue_connection(self, peer):
        peer.buffer = Message.ContinueConnectionMessage().encode()
        assert peer.handle_continue_connection() is True
        assert peer.buffer == b''

    def test_continue_connection_fail_incorrect_data(self, peer):
        peer.buffer = pack('!I', 3)
        assert peer.handle_continue_connection() is False

    @pytest.mark.asyncio
    async def test_handle_handshake(self, peer, monkeypatch):
        peer.is_active = True
        mock_send = AsyncMock()
        with monkeypatch.context() as m:
            m.setattr(peer, 'send_message_to_peer', mock_send)
            result = await peer.handle_handshake()
        assert result is True
        assert mock_send.call_count == 1
        assert isinstance(mock_send.call_args[0][0], Message.HandshakeMessage)

    @pytest.mark.asyncio
    async def test_handle_handshake_fail(self, peer, monkeypatch, caplog):
        peer.is_active = False
        mock_send = AsyncMock()
        with caplog.at_level(logging.ERROR):
            with monkeypatch.context() as m:
                m.setattr(peer, 'send_message_to_peer', mock_send)
                result = await peer.handle_handshake()
            assert 'Произошла ошибка при handshake-e, пир неактивен' in caplog.text
            assert result is False

    @pytest.mark.asyncio
    async def test_read_socket(self, monkeypatch, peer):
        reader = AsyncMock()
        reader.read.return_value = b'xYxYxY'
        with monkeypatch.context() as m:
            m.setattr(peer, 'reader', reader)
            await peer.read_socket()
        assert peer.buffer == b'xYxYxY'

    @pytest.mark.asyncio
    async def test_read_socket_incorrect(self, monkeypatch, peer, caplog):
        reader = AsyncMock()
        reader.read.side_effect = OSError
        with caplog.at_level(logging.ERROR):
            with monkeypatch.context() as m:
                m.setattr(peer, 'reader', reader)
                await peer.read_socket()
            assert peer.is_active is False
            assert 'Таймаут чтения с сокета' in caplog.text

    @pytest.mark.asyncio
    async def test_handle_message_handshake_and_continue(self, peer, caplog):
        with caplog.at_level(logging.ERROR):
            await peer.handle_message(Message.HandshakeMessage(b'\x00' * 32))
            assert 'Обработка Handshake сообщения производится отдельно' in caplog.text
            caplog.clear()
            await peer.handle_message(Message.ContinueConnectionMessage())
            assert 'Обработка ContinueConnection сообщения производится отдельно' in caplog.text

    @pytest.mark.asyncio
    async def test_handle_message_properties(self, peer):
        await peer.handle_message(Message.ChokedMessage())
        assert peer.peer_choked is True
        await peer.handle_message(Message.UnChokedMessage())
        assert peer.peer_choked is False
        await peer.handle_message(Message.InterestedMessage())
        assert peer.peer_interested is True
        await peer.handle_message(Message.NotInterestedMessage())
        assert peer.peer_interested is False

    @pytest.mark.asyncio
    async def test_handle_message_other(self, peer, caplog, monkeypatch):
        with caplog.at_level(logging.INFO):
            with monkeypatch.context() as m:
                mock = AsyncMock()
                m.setattr(peer, 'handle_got_piece', mock)
                message = Message.HaveMessage(1)
                await peer.handle_message(message)
                assert 'got have message' in caplog.text
                assert mock.call_count == 1
                assert isinstance(mock.call_args[0][0], Message.HaveMessage)
                caplog.clear()
                message = Message.PeerSegmentsMessage(bitstring.BitArray(8))
                m.setattr(peer, 'handle_available_piece', mock)
                await peer.handle_message(message)
                assert 'got peer segments message' in caplog.text
                assert mock.call_count == 2
                assert isinstance(mock.call_args[0][0], Message.PeerSegmentsMessage)
                caplog.clear()
                m.setattr(peer, 'handle_piece_request', mock)
                message = Message.RequestsMessage(1, 1, 2)
                await peer.handle_message(message)
                assert mock.call_count == 3
                assert isinstance(mock.call_args[0][0], Message.RequestsMessage)
                caplog.clear()
                m.setattr(peer, 'handle_piece_receive', mock)
                message = Message.SendPieceMessage(1, 1, b'22')
                await peer.handle_message(message)
                assert mock.call_count == 4
                assert isinstance(mock.call_args[0][0], Message.SendPieceMessage)
                message = Message.CancelMessage(1, 1, 2)
                await peer.handle_message(message)
                assert 'got cancel message' in caplog.text

    @pytest.mark.asyncio
    async def test_handle_message_fail(self, peer, caplog):
        with caplog.at_level(logging.ERROR):
            messages = 'fdfdfdfdfdfd'
            await peer.handle_message(messages)
            assert 'Такого типа сообщения нет str'

    @pytest.mark.asyncio
    async def test_close_connection(self, monkeypatch, peer):
        mock_writer_close = AsyncMock()
        mock_reader = AsyncMock
        with monkeypatch.context() as m:
            m.setattr(peer, 'writer', mock_writer_close)
            m.setattr(peer, 'reader', mock_reader)
            await peer.close()
            assert peer.is_active is False
            assert peer.reader is None
            assert mock_writer_close.close.call_count == 1
