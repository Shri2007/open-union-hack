"""Build the registered Firedrill agent's machine-local plan on stdout."""
import hashlib
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parent.parent
stat = root.stat()
identity = hashlib.sha256(
    f"firedrill.root-identity.v1\0{root}\0{stat.st_dev}:{stat.st_ino}".encode()
).hexdigest()
readiness = {"kind": "http", "url": "http://127.0.0.1:0/health", "expect_status": [200]}
plan = {
    "version": 1,
    "descriptor_sha256": sys.argv[1],
    "roots": [{"alias": "app", "path": str(root), "identity_sha256": identity}],
    "services": [{
        "alias": "adapter", "root_alias": "app", "mode": "launch",
        "command": {"executable": sys.executable, "args": ["firedrill/relay_drills.py"]},
        "cwd": ".", "readiness": readiness, "readiness_timeout_ms": 10000,
        "stop_timeout_ms": 5000, "per_drill": False, "port_env": "PORT",
        "env_static": {}, "env_passthrough": [],
    }],
    "driver": {
        "profile": "http.v1", "service_alias": "adapter", "path": "/drill",
        "method": "POST", "stream": "none", "session_header": None,
        "request_template": "task-json", "response_pointer": None,
    },
    "state_hooks": [{
        "domain_alias": "test-coalition", "root_alias": "app",
        "path": "firedrill/reset_coalition.py",
        "sha256": hashlib.sha256((root / "firedrill/reset_coalition.py").read_bytes()).hexdigest(),
        "runtime": {"executable": sys.executable, "args": []}, "timeout_ms": 30000,
    }],
    "max_parallel_drills": 1,
}
print(json.dumps(plan, indent=2))
