#!/usr/bin/env python3
"""Expose immutable F8 loopback server only inside the Compose private network."""
import asyncio
import os
import signal
import subprocess


async def relay(reader, writer):
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    finally:
        writer.close()


async def handle(reader, writer):
    try:
        upstream_reader, upstream_writer = await asyncio.open_connection("127.0.0.1", 8126)
    except OSError:
        writer.close()
        return
    await asyncio.gather(relay(reader, upstream_writer), relay(upstream_reader, writer), return_exceptions=True)


async def main():
    argv = ["python", "/assets/overlay/night_server.py", "--catalog", "/assets/catalog/catalog-bundle.json",
            "--index-dir", "/assets/index", "--host", "127.0.0.1", "--port", "8126",
            "--threads", "6", "--encoder", "so400m", "--route", "onnx640"]
    child = subprocess.Popen(argv, env=os.environ.copy())
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, child.terminate)
    try:
        async with await asyncio.start_server(handle, "0.0.0.0", 8127) as server:
            await asyncio.to_thread(child.wait)
            server.close()
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                await asyncio.to_thread(child.wait, 10)
            except subprocess.TimeoutExpired:
                child.kill()
                await asyncio.to_thread(child.wait)
    raise SystemExit(child.returncode)


if __name__ == "__main__":
    asyncio.run(main())
