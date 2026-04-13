#!/usr/bin/env python3
"""
Start, stop, and inspect local MinIO and DynamoDB Local processes.
"""

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


HOST = "127.0.0.1"
MINIO_API_PORT = 9000
MINIO_CONSOLE_PORT = 9001
DYNAMODB_PORT = 8000
READY_TIMEOUT_SECONDS = 30
SHUTDOWN_TIMEOUT_SECONDS = 2.0


@dataclass(frozen=True)
class ServiceConfig:
    name: str
    pidfile: Path
    stdout_log: Path
    stderr_log: Path
    ports: tuple[int, ...]
    process_patterns: tuple[str, ...]


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
LOG_DIR = ROOT_DIR / "logs"
DATA_DIR = ROOT_DIR / "var"

SERVICES = {
    "minio": ServiceConfig(
        name="MinIO",
        pidfile=DATA_DIR / "minio.pid",
        stdout_log=LOG_DIR / "minio.stdout",
        stderr_log=LOG_DIR / "minio.stderr",
        ports=(MINIO_API_PORT, MINIO_CONSOLE_PORT),
        process_patterns=("minio server",),
    ),
    "dynamodb": ServiceConfig(
        name="DynamoDB Local",
        pidfile=DATA_DIR / "dynamodb_local.pid",
        stdout_log=LOG_DIR / "dynamodb_local.stdout",
        stderr_log=LOG_DIR / "dynamodb_local.stderr",
        ports=(DYNAMODB_PORT,),
        process_patterns=("DynamoDBLocal.jar",),
    ),
}


def ensure_dirs() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def read_pid(pidfile: Path) -> int | None:
    if not pidfile.exists():
        return None
    try:
        return int(pidfile.read_text().strip())
    except (OSError, ValueError):
        return None


def process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def remove_stale_pidfile(config: ServiceConfig) -> None:
    pid = read_pid(config.pidfile)
    if pid is None:
        return
    if not process_exists(pid):
        config.pidfile.unlink(missing_ok=True)


def is_port_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((HOST, port)) == 0


def port_owner(port: int) -> str | None:
    lsof = shutil.which("lsof")
    if lsof is None:
        return None
    result = subprocess.run(
        [lsof, "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
        capture_output=True,
        text=True,
        check=False,
    )
    output = result.stdout.strip()
    if not output:
        return None
    return output


def port_pids(port: int) -> set[int]:
    lsof = shutil.which("lsof")
    if lsof is None:
        return set()
    result = subprocess.run(
        [lsof, "-ti", f"-iTCP:{port}", "-sTCP:LISTEN"],
        capture_output=True,
        text=True,
        check=False,
    )
    pids: set[int] = set()
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pids.add(int(line))
        except ValueError:
            continue
    return pids


def pids_matching_pattern(pattern: str) -> set[int]:
    pgrep = shutil.which("pgrep")
    if pgrep is None:
        return set()
    result = subprocess.run(
        [pgrep, "-f", pattern],
        capture_output=True,
        text=True,
        check=False,
    )
    pids: set[int] = set()
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pids.add(int(line))
        except ValueError:
            continue
    return pids


def discover_running_service_pid(config: ServiceConfig) -> int | None:
    if not all(is_port_listening(port) for port in config.ports):
        return None
    matching_pids: set[int] = set()
    for pattern in config.process_patterns:
        matching_pids.update(pid for pid in pids_matching_pattern(pattern) if process_exists(pid))
    if not matching_pids:
        return None
    for port in config.ports:
        if not (port_pids(port) & matching_pids):
            return None
    return min(matching_pids)


def tail_lines(path: Path, max_lines: int = 20) -> str:
    if not path.exists():
        return ""
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-max_lines:])


def minio_env() -> dict[str, str]:
    env = os.environ.copy()
    env["MINIO_ROOT_USER"] = "minioadmin"
    env["MINIO_ROOT_PASSWORD"] = "minioadmin"
    env["MINIO_API_CORS_ALLOW_ORIGIN"] = "*"
    return env


def dynamodb_env() -> dict[str, str]:
    env = os.environ.copy()
    if sys.platform == "darwin":
        brew = shutil.which("brew")
        if brew:
            result = subprocess.run(
                [brew, "--prefix", "openjdk"],
                capture_output=True,
                text=True,
                check=False,
            )
            java_home = result.stdout.strip()
            if result.returncode == 0 and java_home:
                env["JAVA_HOME"] = java_home
                env["PATH"] = f"{java_home}/bin:{env.get('PATH', '')}"
    return env


def service_command(service: str) -> tuple[list[str], dict[str, str]]:
    if service == "minio":
        command = [
            str(SCRIPT_DIR / "minio"),
            "server",
            "--address",
            f"{HOST}:{MINIO_API_PORT}",
            "--console-address",
            f"{HOST}:{MINIO_CONSOLE_PORT}",
            str(DATA_DIR),
        ]
        return command, minio_env()
    if service == "dynamodb":
        jar_path = SCRIPT_DIR / "DynamoDBLocal.jar"
        if not jar_path.exists():
            raise RuntimeError(f"{jar_path} does not exist")
        command = [
            "java",
            f"-Djava.library.path={SCRIPT_DIR / 'DynamoDBLocal_lib'}",
            "-jar",
            str(jar_path),
            "-sharedDb",
            "-dbPath",
            str(DATA_DIR),
            "-port",
            str(DYNAMODB_PORT),
        ]
        return command, dynamodb_env()
    raise RuntimeError(f"Unknown service {service}")


def report_port_conflicts(config: ServiceConfig) -> bool:
    conflict = False
    for port in config.ports:
        if not is_port_listening(port):
            continue
        conflict = True
        print(f"{config.name} cannot start because port {port} is already in use.")
        owner = port_owner(port)
        if owner:
            print(owner)
    return conflict


def wait_for_service(config: ServiceConfig, process: subprocess.Popen[bytes]) -> None:
    print(
        f"Waiting for {config.name} to be ready on "
        + ", ".join(f"{HOST}:{port}" for port in config.ports)
        + " ..."
    )
    for attempt in range(1, READY_TIMEOUT_SECONDS + 1):
        if process.poll() is not None:
            config.pidfile.unlink(missing_ok=True)
            print(f"{config.name} exited during startup with code {process.returncode}.")
            if config.stderr_log.exists():
                print(f"stderr log: {config.stderr_log}")
                stderr_tail = tail_lines(config.stderr_log)
                if stderr_tail:
                    print(stderr_tail)
            if config.stdout_log.exists():
                print(f"stdout log: {config.stdout_log}")
                stdout_tail = tail_lines(config.stdout_log)
                if stdout_tail:
                    print(stdout_tail)
            raise SystemExit(1)
        if all(is_port_listening(port) for port in config.ports):
            print(f"{config.name} is ready.")
            return
        print(f"  Waiting for {config.name} to be ready ({attempt})...")
        time.sleep(1)
    print(f"{config.name} did not become ready within {READY_TIMEOUT_SECONDS} seconds.")
    print("Ports being checked:")
    for port in config.ports:
        print(f"  {HOST}:{port}")
    raise SystemExit(1)


def start_service(service: str) -> None:
    ensure_dirs()
    config = SERVICES[service]
    remove_stale_pidfile(config)
    existing_pid = read_pid(config.pidfile)
    if existing_pid and process_exists(existing_pid):
        if all(is_port_listening(port) for port in config.ports):
            print(f"{config.name} is already running (PID: {existing_pid}).")
            return
        print(f"{config.name} pidfile exists for PID {existing_pid}, but readiness checks failed.")
        return
    discovered_pid = discover_running_service_pid(config)
    if discovered_pid is not None:
        config.pidfile.write_text(str(discovered_pid))
        print(f"{config.name} is already running (PID: {discovered_pid}).")
        return
    if report_port_conflicts(config):
        raise SystemExit(1)
    command, env = service_command(service)
    print(f"Starting {config.name} ...")
    print("Ports:")
    for port in config.ports:
        print(f"  {HOST}:{port}")
    with config.stdout_log.open("w") as stdout_file, config.stderr_log.open("w") as stderr_file:
        process = subprocess.Popen(
            command,
            stdout=stdout_file,
            stderr=stderr_file,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            cwd=str(ROOT_DIR),
            env=env,
        )
    config.pidfile.write_text(str(process.pid))
    print(f"{config.name} started in the background (PID: {process.pid}).")
    print(f"stdout log: {config.stdout_log}")
    print(f"stderr log: {config.stderr_log}")
    wait_for_service(config, process)


def stop_service(service: str) -> None:
    config = SERVICES[service]
    pid = read_pid(config.pidfile)
    if pid is None:
        discovered_pid = discover_running_service_pid(config)
        if discovered_pid is not None:
            config.pidfile.write_text(str(discovered_pid))
            pid = discovered_pid
    if pid is None:
        print(f"{config.name} is not running (no pidfile).")
        return
    if not process_exists(pid):
        print(f"{config.name} pidfile exists but PID {pid} is not running. Removing stale pidfile.")
        config.pidfile.unlink(missing_ok=True)
        return
    print(f"Stopping {config.name} (PID: {pid})...")
    os.kill(pid, signal.SIGTERM)
    deadline = time.time() + SHUTDOWN_TIMEOUT_SECONDS
    while time.time() < deadline:
        if not process_exists(pid):
            config.pidfile.unlink(missing_ok=True)
            print(f"{config.name} stopped.")
            return
        time.sleep(0.1)
    print(f"{config.name} (PID: {pid}) did not shut down gracefully. Forcing kill.")
    os.kill(pid, signal.SIGKILL)
    config.pidfile.unlink(missing_ok=True)
    print(f"{config.name} stopped.")


def status_service(service: str) -> None:
    config = SERVICES[service]
    remove_stale_pidfile(config)
    pid = read_pid(config.pidfile)
    if pid is None:
        discovered_pid = discover_running_service_pid(config)
        if discovered_pid is not None:
            config.pidfile.write_text(str(discovered_pid))
            pid = discovered_pid
    if pid and process_exists(pid):
        print(f"{config.name} is running (PID: {pid}).")
    else:
        print(f"{config.name} is not running.")
    for port in config.ports:
        state = "listening" if is_port_listening(port) else "not listening"
        print(f"  {HOST}:{port} {state}")


def debug_service(service: str) -> None:
    config = SERVICES[service]
    command, _ = service_command(service)
    print(f"service={service}")
    print(f"root_dir={ROOT_DIR}")
    print(f"log_dir={LOG_DIR}")
    print(f"data_dir={DATA_DIR}")
    print(f"pidfile={config.pidfile}")
    print(f"stdout_log={config.stdout_log}")
    print(f"stderr_log={config.stderr_log}")
    print("ports=" + ", ".join(str(port) for port in config.ports))
    print("command=" + " ".join(command))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Control local MinIO and DynamoDB Local services.")
    parser.add_argument("service", choices=sorted(SERVICES))
    parser.add_argument("action", choices=["start", "stop", "restart", "status", "wait", "debug"])
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.action == "start":
        start_service(args.service)
    elif args.action == "stop":
        stop_service(args.service)
    elif args.action == "restart":
        stop_service(args.service)
        start_service(args.service)
    elif args.action == "status":
        status_service(args.service)
    elif args.action == "wait":
        config = SERVICES[args.service]
        for attempt in range(1, READY_TIMEOUT_SECONDS + 1):
            if all(is_port_listening(port) for port in config.ports):
                print(f"{config.name} is ready.")
                return 0
            print(f"  Waiting for {config.name} to be ready ({attempt})...")
            time.sleep(1)
        print(f"{config.name} is not ready.")
        return 1
    elif args.action == "debug":
        debug_service(args.service)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
