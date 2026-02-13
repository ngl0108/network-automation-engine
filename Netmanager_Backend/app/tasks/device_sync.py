try:
    from celery import shared_task
except ModuleNotFoundError:
    def shared_task(*args, **kwargs):
        def decorator(fn):
            return fn

        if args and callable(args[0]) and not kwargs:
            return args[0]
        return decorator

@shared_task(name="app.tasks.device_sync.ssh_sync_device")
def ssh_sync_device(device_id: int):
    from app.services.device_sync_service import DeviceSyncService
    return DeviceSyncService.sync_device_job(device_id)


@shared_task(name="app.tasks.device_sync.enqueue_ssh_sync_batch")
def enqueue_ssh_sync_batch(device_ids, interval_seconds: float = 3.0, jitter_seconds: float = 0.5):
    """
    Schedule ssh_sync_device tasks with countdown spacing to avoid SSH bursts.
    device_ids: list[int]
    """
    try:
        ids = [int(x) for x in (device_ids or [])]
    except Exception:
        ids = []

    if not ids:
        return {"scheduled": 0}

    interval = float(interval_seconds or 0)
    jitter = float(jitter_seconds or 0)
    if interval < 0:
        interval = 0
    if jitter < 0:
        jitter = 0

    import random

    scheduled = 0
    for i, d_id in enumerate(ids):
        countdown = (i * interval) + (random.random() * jitter if jitter else 0)
        ssh_sync_device.apply_async(args=[d_id], countdown=countdown)
        scheduled += 1

    return {"scheduled": scheduled, "interval_seconds": interval, "jitter_seconds": jitter}
