import os
import re
from pathlib import Path

def test_socket_events():
    root = Path(__file__).resolve().parent.parent

    # Find frontend events
    web_dir = root / "apps" / "web" / "src"
    frontend_on = set()
    frontend_emit = set()

    frontend_files = list(web_dir.rglob("*.tsx")) + list(web_dir.rglob("*.ts"))
    for f in frontend_files:
        content = f.read_text(encoding="utf-8")
        # match socket.on('event') or socket.on("event")
        for match in re.finditer(r'socket\.on\(\s*[\'"]([^\'"]+)[\'"]', content):
            frontend_on.add(match.group(1))
        # match socket.emit('event') or socket.emit("event")
        for match in re.finditer(r'socket\.emit\(\s*[\'"]([^\'"]+)[\'"]', content):
            frontend_emit.add(match.group(1))

    # Find backend events
    api_dir = root / "apps" / "api"
    backend_on = set()
    backend_emit = set()

    backend_files = list(api_dir.rglob("*.py"))
    for f in backend_files:
        content = f.read_text(encoding="utf-8")
        # match @sio.on('event') or @sio.on("event")
        for match in re.finditer(r'@sio\.on\(\s*[\'"]([^\'"]+)[\'"]', content):
            backend_on.add(match.group(1))
        # match await sio.emit('event') or await sio.emit("event")
        for match in re.finditer(r'sio\.emit\(\s*[\'"]([^\'"]+)[\'"]', content):
            backend_emit.add(match.group(1))

    # Built-in socket.io events
    builtin = {"connect", "disconnect"}

    frontend_on -= builtin
    frontend_emit -= builtin
    backend_on -= builtin
    backend_emit -= builtin

    # Find mismatches
    frontend_listening_to_nothing = frontend_on - backend_emit
    backend_listening_to_nothing = backend_on - frontend_emit

    frontend_emitting_to_nowhere = frontend_emit - backend_on
    backend_emitting_to_nowhere = backend_emit - frontend_on

    assert not frontend_listening_to_nothing, f"Frontend listens to events not emitted by backend: {frontend_listening_to_nothing}"
    assert not backend_listening_to_nothing, f"Backend listens to events not emitted by frontend: {backend_listening_to_nothing}"
    assert not frontend_emitting_to_nowhere, f"Frontend emits events not listened to by backend: {frontend_emitting_to_nowhere}"
    assert not backend_emitting_to_nowhere, f"Backend emits events not listened to by frontend: {backend_emitting_to_nowhere}"

if __name__ == "__main__":
    test_socket_events()
    print("Socket events matched perfectly!")
