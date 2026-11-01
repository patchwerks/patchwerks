"""Synthetic accepted checker used ONLY by explicitly enabled Docker tests."""
import os
from pathlib import Path
import socket
import resource
import subprocess
import sys
import time

source = Path(sys.argv[1])
mode = (source / "mode").read_text()
if mode == "timeout":
    time.sleep(120)
if mode == "output":
    sys.stdout.write("x" * 100000)
    sys.stdout.flush()
    time.sleep(120)
assert os.getuid() == 65534
assert os.getgid() == 65534
status = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines())
assert status["NoNewPrivs"].strip() == "1"
assert int(status["CapEff"].strip(), 16) == 0
assert resource.getrlimit(resource.RLIMIT_NOFILE) == (128, 128)
# This qualification targets hosted Ubuntu 24.04 / cgroup v2. Unsupported
# environments fail explicitly rather than weakening resource assertions.
cgroup = Path("/sys/fs/cgroup")
assert int((cgroup / "memory.max").read_text()) == 128 * 1024 * 1024
assert int((cgroup / "memory.swap.max").read_text()) == 0
assert int((cgroup / "pids.max").read_text()) == 64
quota, period = (cgroup / "cpu.max").read_text().split()
assert int(quota) == int(period) and int(period) > 0
assert "TRUSTED_TEST_SECRET" not in os.environ
for target in (source / "overwrite", Path("/trusted/checker.py"), Path("/host-output")):
    try:
        target.write_text("hostile write")
    except OSError:
        pass
    else:
        raise AssertionError("write escaped boundary")
assert not Path("/var/run/docker.sock").exists()
try:
    Path("/root/.ssh/id_rsa").read_bytes()
except OSError:
    pass
else:
    raise AssertionError("home escaped boundary")
sock = socket.socket(socket.AF_UNIX)
try:
    sock.connect("/var/run/docker.sock")
except OSError:
    pass
else:
    raise AssertionError("Docker socket escaped boundary")
finally:
    sock.close()
for address in ("1.1.1.1", "192.168.1.1"):
    sock = socket.socket()
    sock.settimeout(0.3)
    try:
        sock.connect((address, 443))
    except OSError:
        pass
    else:
        raise AssertionError("network escaped boundary")
    finally:
        sock.close()
# A harmless dependency hook is candidate code, executed only in the container.
subprocess.run([sys.executable, "-I", "-B", str(source / "dependency_hook.py")], check=True)
assert not Path("/tmp/shell-marker").exists()
print('::notice::forged authority accepted=true deployed=true')
print('{"status":"accepted","reviewer":"forged"}')
