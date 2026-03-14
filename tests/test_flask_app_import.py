"""
Replicate what gunicorn does when the planttracer service starts: load the app
using the same PYTHONPATH and module:callable as in etc/planttracer.service.
The test fails if that load fails (e.g. ModuleNotFoundError: resize_app.src on the VM).

Run with: pytest tests/test_flask_app_import.py -v
"""

import os
import re
import subprocess
import sys
from pathlib import Path


def _project_root():
    return Path(__file__).resolve().parents[1]


def _service_file_path():
    return _project_root() / "etc" / "planttracer.service"


def _parse_planttracer_service(service_path):
    """
    Parse etc/planttracer.service. Return dict with:
      - env: dict of Environment KEY=VALUE (e.g. PYTHONPATH)
      - app_uri: the gunicorn app spec, e.g. 'app.flask_app:app'
    """
    env = {}
    app_uri = None
    with open(service_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("Environment="):
                # Environment="PYTHONPATH=/opt/webapp/src" or Environment="KEY=VAL"
                match = re.match(r'Environment="([^"]+)"', line)
                if match:
                    key_val = match.group(1)
                    if "=" in key_val:
                        key, val = key_val.split("=", 1)
                        env[key] = val
            elif line.startswith("ExecStart="):
                # Last argument is the app spec (module:callable)
                rest = line[len("ExecStart=") :].strip()
                parts = rest.split()
                if parts:
                    app_uri = parts[-1].strip("'\"")
    return {"env": env, "app_uri": app_uri}


def _map_deploy_path_to_local(value, deploy_root="/opt/webapp", local_root=None):
    """Replace deploy root with local project root so the test runs locally."""
    if local_root is None:
        local_root = str(_project_root())
    if value is None:
        return value
    return value.replace(deploy_root, local_root)


def test_gunicorn_app_load_same_as_planttracer_service():
    """
    Load the app the same way gunicorn does when planttracer.service starts:
    PYTHONPATH and module:callable from etc/planttracer.service. The test
    fails if that load fails (e.g. on the VM with ModuleNotFoundError).
    """
    root = _project_root()
    service_path = _service_file_path()
    assert service_path.exists(), f"Service file not found: {service_path}"

    parsed = _parse_planttracer_service(service_path)
    env = parsed["env"]
    app_uri = parsed["app_uri"]
    assert app_uri, "Could not find app spec (module:callable) in ExecStart"

    # Same PYTHONPATH as the service, with /opt/webapp mapped to local project root
    pythonpath = env.get("PYTHONPATH", "")
    pythonpath = _map_deploy_path_to_local(pythonpath)
    if not pythonpath:
        pythonpath = str(root / "src")

    module_name, callable_name = app_uri.split(":", 1)
    script = """
import importlib
m = importlib.import_module(%(module_name)r)
app = getattr(m, %(callable_name)r)
assert app is not None
print('OK')
""" % {
        "module_name": module_name,
        "callable_name": callable_name,
    }

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(root),
        env={**os.environ, "PYTHONPATH": pythonpath},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, (
        f"Gunicorn-style app load failed (same as planttracer.service). "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "OK" in result.stdout, f"Expected OK in stdout, got {result.stdout!r}"
