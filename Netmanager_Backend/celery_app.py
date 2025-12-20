from celery import Celery

celery_app = Celery(
    "netmanager",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1",
    include=["app.tasks.monitoring", "app.tasks.config"]  # 태스크 모듈들
)

# Celery 설정 (하드코딩으로 간단히)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Seoul",
    enable_utc=False,
    beat_schedule={
        "monitor-all-devices-every-minute": {
            "task": "app.tasks.monitoring.monitor_all_devices",
            "schedule": 60.0,  # 60초마다
        },
    },
)