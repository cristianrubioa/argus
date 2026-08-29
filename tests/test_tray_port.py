from argus.tray import port


def test_resolve_port_reads_configured_value(tmp_path, monkeypatch):
    # Setup
    port_file = tmp_path / "port"
    port_file.write_text("ARGUS_WEB_PORT=9001\n")
    monkeypatch.setattr(port, "PORT_FILE", str(port_file))
    # Action & Expected
    assert port.resolve_port() == 9001


def test_resolve_port_falls_back_when_file_absent(tmp_path, monkeypatch):
    # Setup
    monkeypatch.setattr(port, "PORT_FILE", str(tmp_path / "does-not-exist"))
    # Action & Expected
    assert port.resolve_port() == port.DEFAULT_PORT


def test_resolve_port_falls_back_when_file_has_no_matching_line(tmp_path, monkeypatch):
    # Setup
    port_file = tmp_path / "port"
    port_file.write_text("garbage\n")
    monkeypatch.setattr(port, "PORT_FILE", str(port_file))
    # Action & Expected
    assert port.resolve_port() == port.DEFAULT_PORT
