from __future__ import annotations

import tempfile
import threading
from unittest.mock import patch

import anyio
import pytest


@pytest.mark.parametrize('anyio_backend', ['asyncio', 'trio'])
@pytest.mark.anyio
async def test_cancellation_during_rollover(anyio_backend):
    entered = threading.Event()
    release = threading.Event()
    original = tempfile.TemporaryFile
    def create(**kwargs):
        entered.set()
        assert release.wait(3), 'controller did not release worker'
        return original(**kwargs)

    async with anyio.SpooledTemporaryFile(max_size=8) as f:
        await f.write(b'aaaa')
        scope = anyio.CancelScope()
        async def writer():
            with scope:
                await f.write(b'bbbbbbbb')
        with patch('anyio._core._tempfile.tempfile.TemporaryFile', create):
            async with anyio.create_task_group() as tg:
                tg.start_soon(writer)
                with anyio.fail_after(3):
                    while not entered.is_set():
                        await anyio.sleep(0)
                scope.cancel()
                release.set()
        await f.write(b'cc')
        await f.seek(0)
        assert await f.read() == b'aaaabbbbbbbbcc'


@pytest.mark.parametrize('anyio_backend', ['asyncio', 'trio'])
@pytest.mark.anyio
async def test_failed_rollover_retry(anyio_backend, tmp_path):
    missing = tmp_path / 'missing'
    async with anyio.SpooledTemporaryFile(max_size=8, dir=missing) as f:
        await f.write(b'aaaa')
        with pytest.raises(FileNotFoundError):
            await f.write(b'bbbbbbbb')
        assert await f.tell() == 12
        missing.mkdir()
        await f.write(b'cc')
        await f.seek(0)
        assert await f.read() == b'aaaabbbbbbbbcc'
