import bitstring
import pytest
import asyncio
from peer_connection import PeerConnection
from unittest.mock import AsyncMock, MagicMock, patch
from pubsub import pub
from requests_receiver import PeerReceiver, RequestsReceiver


@pytest.fixture
def mock_peer_connection():
    with patch('peer_connection.PeerConnection', autospec=True) as MockPeerConnection:
        yield MockPeerConnection


@pytest.fixture
def peer_receiver(mock_peer_connection):
    sock = MagicMock()
    address = ('127.0.0.1', 6881)
    receiver = PeerReceiver(sock, address)
    return receiver


class TestRequestsReceiver:
    @pytest.mark.asyncio
    async def test_get_info_hash(self, monkeypatch):
        mock_connect = AsyncMock(return_value=True)
        mock_run = AsyncMock()
        with monkeypatch.context() as m:
            mock_pub_subscribe = MagicMock()
            m.setattr(pub, "subscribe", mock_pub_subscribe)

            peer = PeerReceiver(sock=MagicMock(), address=("127.0.0.1", 8080))

            m.setattr(peer, 'connect', mock_connect)
            m.setattr(peer, 'run', mock_run)

            peer._get_handshake = MagicMock()
            peer.info_hash = "some_info_hash"

            result = await peer.get_info_hash()

            mock_connect.assert_called_once()
            mock_run.assert_called_once()

            assert result == "some_info_hash"

    @pytest.mark.asyncio
    async def test_add_peer(self, monkeypatch):
        mock_peer_receiver = AsyncMock()
        mock_peer_receiver.get_info_hash.return_value = "some_info_hash"

        mock_pub_send = MagicMock()
        with monkeypatch.context() as m:
            m.setattr(pub, "sendMessage", mock_pub_send)
            m.setattr(PeerReceiver, "get_info_hash", mock_peer_receiver)
            receiver = RequestsReceiver()

            await receiver.add_peer(MagicMock(), ("127.0.0.1", 8080))

            mock_peer_receiver.assert_called_once()

    def test_handle_handshake_for_buffer(self, monkeypatch):
        mock_handshake_message = MagicMock()
        mock_decode = MagicMock(return_value=mock_handshake_message)
        monkeypatch.setattr("Message.HandshakeMessage.decode", mock_decode)

        peer = PeerReceiver(sock=MagicMock(), address=("127.0.0.1", 8080))
        peer.buffer = b'\x13' + b'a' * 67

        result = peer.handle_handshake_for_buffer()

        assert result is True
        mock_decode.assert_called_once_with(b'\x13' + b'a' * 67)
        assert peer.handshake is True
        assert len(peer.buffer) == 0

    @pytest.mark.asyncio
    async def test_run_server(self, monkeypatch):
        mock_sock_accept = AsyncMock(side_effect=[
            (MagicMock(), ("127.0.0.1", 8080)),
            asyncio.TimeoutError()
        ])

        mock_add_peer = AsyncMock()

        receiver = RequestsReceiver()

        monkeypatch.setattr(asyncio.get_event_loop(), 'sock_accept', mock_sock_accept)
        monkeypatch.setattr(receiver, 'add_peer', mock_add_peer)

        server_task = asyncio.create_task(receiver._run_server())
        await asyncio.sleep(0.2)
        server_task.cancel()
        assert mock_sock_accept.call_count == 3

    @pytest.mark.asyncio
    async def test_run(self, peer_receiver, mock_peer_connection, monkeypatch):
        peer_receiver.already_running = False
        mock_peer_connection = AsyncMock()
        with monkeypatch.context() as m:
            m.setattr(PeerConnection, 'run', mock_peer_connection)
            await peer_receiver.run()

            mock_peer_connection.assert_awaited_once()
            assert peer_receiver.already_running is True

    @pytest.mark.asyncio
    async def test_connect_failure(self, peer_receiver):
        mock_open_connection = AsyncMock(side_effect=OSError)
        monkeypatch = patch('asyncio.open_connection', mock_open_connection)

        with monkeypatch:
            result = await peer_receiver.connect()

        mock_open_connection.assert_awaited_once_with(sock=peer_receiver.sock)
        assert result is False
        assert peer_receiver.already_connected is False
        assert peer_receiver.is_active is False

    @pytest.mark.asyncio
    async def test_connect_success(self, peer_receiver, mock_peer_connection):
        mock_open_connection = AsyncMock(return_value=(MagicMock(), MagicMock()))
        monkeypatch = patch('asyncio.open_connection', mock_open_connection)

        with monkeypatch:
            result = await peer_receiver.connect()

        mock_open_connection.assert_awaited_once_with(sock=peer_receiver.sock)
        assert result is True
        assert peer_receiver.already_connected is True
        assert peer_receiver.is_active is True

    @pytest.mark.asyncio
    async def test_initiate_bitfield(self, peer_receiver):
        number_of_pieces = 10
        bitfield_length = number_of_pieces if number_of_pieces % 8 == 0 else number_of_pieces + 8 - number_of_pieces % 8
        our_bitfield = bitstring.BitArray(bitfield_length)

        await peer_receiver.initiate_bitfield(number_of_pieces, our_bitfield)

        assert len(peer_receiver.bitfield) == bitfield_length

    @pytest.mark.asyncio
    async def test_handle_handshake_already_sent(self, peer_receiver):
        peer_receiver.already_sent_handshake = True

        result = await peer_receiver.handle_handshake()

        assert result is True

    @pytest.mark.asyncio
    async def test_handle_handshake(self, peer_receiver, monkeypatch):
        peer_receiver.already_sent_handshake = False
        mock_handle_handshake = AsyncMock()
        with monkeypatch.context() as m:
            m.setattr(PeerConnection, 'handle_handshake', mock_handle_handshake)
            result = await peer_receiver.handle_handshake()

            mock_handle_handshake.assert_awaited_once()

