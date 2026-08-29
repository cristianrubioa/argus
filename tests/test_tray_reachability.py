import socket

from argus.tray import reachability


def test_is_dashboard_reachable_true_when_something_is_listening():
    # Setup
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listening_port = listener.getsockname()[1]
    # Action & Expected
    assert reachability.is_dashboard_reachable(listening_port) is True
    listener.close()


def test_is_dashboard_reachable_false_when_nothing_is_listening():
    # Setup
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    closed_port = listener.getsockname()[1]
    listener.close()
    # Action & Expected
    assert reachability.is_dashboard_reachable(closed_port) is False


def test_is_dashboard_reachable_false_on_timeout(monkeypatch):
    # Setup
    def _raise_timeout(*args, **kwargs):
        raise TimeoutError

    monkeypatch.setattr(socket, "create_connection", _raise_timeout)
    # Action & Expected
    assert reachability.is_dashboard_reachable(9999) is False
