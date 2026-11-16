import asyncio
from datetime import UTC, datetime

from apscheduler.events import EVENT_JOB_EXECUTED


async def test_scheduled_run_and_shutdown(service):
    search = service.search
    finished = asyncio.Event()
    search.scheduler.add_listener(lambda event: finished.set(), EVENT_JOB_EXECUTED)
    job = search.scheduler.get_job("feeds")
    assert job.trigger.interval.total_seconds() == 1800
    job.modify(next_run_time=datetime.now(UTC))
    search.scheduler.start()
    try:
        await asyncio.wait_for(finished.wait(), timeout=5)
        assert search.last_run is not None
    finally:
        await search.close()
        await asyncio.sleep(0)
    assert not search.scheduler.running
