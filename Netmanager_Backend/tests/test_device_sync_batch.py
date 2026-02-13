import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.tasks import device_sync


def test_enqueue_ssh_sync_batch_schedules_with_countdown(monkeypatch):
    scheduled = []

    def fake_apply_async(*, args=None, countdown=None, **kwargs):
        scheduled.append((args, countdown))
        return None

    monkeypatch.setattr(device_sync.ssh_sync_device, "apply_async", fake_apply_async, raising=False)

    res = device_sync.enqueue_ssh_sync_batch([10, 20, 30], interval_seconds=2.0, jitter_seconds=0.0)
    assert res["scheduled"] == 3

    assert scheduled[0][0] == [10]
    assert scheduled[0][1] == 0.0
    assert scheduled[1][0] == [20]
    assert scheduled[1][1] == 2.0
    assert scheduled[2][0] == [30]
    assert scheduled[2][1] == 4.0
