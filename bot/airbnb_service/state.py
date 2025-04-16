import asyncio

scheduler_task: asyncio.Task | None = None
scheduler_running: bool = False
