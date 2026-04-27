from __future__ import annotations

import socket
import subprocess
import time
import uuid
from pathlib import Path

import httpx

from .base import ChatInstance


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _docker(*args: str, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(['docker', *args],
                           check=check,
                           capture_output=capture,
                           text=True)


class DockerChatRunner:
    def __init__(self, *, image: str = 'lazyrag-chat:latest',
                 mount_target: str = '/app/chat',
                 container_port: int = 8046,
                 health_path: str = '/healthz',
                 startup_timeout_s: float = 60.0,
                 stop_timeout_s: float = 10.0,
                 network: str | None = None,
                 extra_args: list[str] | None = None) -> None:
        self.image = image
        self.mount_target = mount_target
        self.container_port = container_port
        self.health_path = health_path
        self.startup_timeout_s = startup_timeout_s
        self.stop_timeout_s = stop_timeout_s
        self.network = network
        self.extra_args = list(extra_args or [])
        self._containers: dict[str, str] = {}

    def launch(self, *, source_dir: Path, label: str,
               env: dict | None = None,
               owner_thread_id: str | None = None) -> ChatInstance:
        port = _free_port()
        chat_id = f'chat-{label}-{uuid.uuid4().hex[:6]}'
        name = f'evo-{chat_id}'
        cmd = ['run', '-d', '--rm',
                '--name', name,
                '-p', f'127.0.0.1:{port}:{self.container_port}',
                '-v', f'{Path(source_dir).resolve()}:{self.mount_target}:ro']
        if self.network:
            cmd += ['--network', self.network]
        for k, v in (env or {}).items():
            cmd += ['-e', f'{k}={v}']
        cmd += self.extra_args + [self.image]

        _docker(*cmd)
        self._containers[chat_id] = name
        base_url = f'http://127.0.0.1:{port}'
        instance = ChatInstance(
            chat_id=chat_id, pid=None, port=port,
            base_url=base_url, source_dir=Path(source_dir),
            health_url=f'{base_url}{self.health_path}',
            status='starting', owner_thread_id=owner_thread_id,
        )
        if not self._wait_healthy(instance, name):
            self.stop(chat_id)
            instance.status = 'unhealthy'
            raise RuntimeError(
                f'docker chat {chat_id} failed startup; '
                f'see `docker logs {name}`')
        instance.status = 'healthy'
        return instance

    def stop(self, chat_id: str) -> None:
        name = self._containers.pop(chat_id, None)
        if name is None:
            return
        _docker('stop', '-t', str(int(self.stop_timeout_s)), name,
                check=False)

    def _wait_healthy(self, instance: ChatInstance, name: str) -> bool:
        deadline = time.time() + self.startup_timeout_s
        while time.time() < deadline:
            if not _container_running(name):
                return False
            try:
                if httpx.get(instance.health_url, timeout=1.0).is_success:
                    return True
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        return False


def _container_running(name: str) -> bool:
    r = _docker('inspect', '-f', '{{.State.Running}}', name,
                 check=False)
    return r.returncode == 0 and r.stdout.strip().lower() == 'true'
