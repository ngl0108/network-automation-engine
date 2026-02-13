import os
from celery import Celery
from celery.schedules import crontab
from app.core.logging_config import configure_logging

configure_logging()

# 1. Celery 인스턴스 생성 (Redis 설정)
# [FIX] Docker 환경 호환성을 위해 환경변수 우선 사용 (localhost -> redis)
broker_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
backend_url = os.getenv("REDIS_URL", "redis://localhost:6379/0") # 같은 Redis 사용

celery_app = Celery(
    "netmanager",
    broker=broker_url,
    backend=backend_url,
    include=["app.tasks.monitoring", "app.tasks.config", "app.tasks.maintenance", "app.tasks.discovery", "app.tasks.neighbor_crawl", "app.tasks.topology_refresh", "app.tasks.device_sync", "app.tasks.syslog_ingest", "app.tasks.compliance", "app.tasks.smart_alerting"]  # 태스크 모듈들
)

# [핵심 수정] 이 줄이 없으면 @shared_task가 Redis 설정을 무시하고 RabbitMQ를 찾습니다.
celery_app.set_default()

# 2. Celery 상세 설정
try:
    from kombu import Exchange, Queue
except ModuleNotFoundError:
    Exchange = None
    Queue = None

discovery_rate_limit = os.getenv("DISCOVERY_TASK_RATE_LIMIT", "30/m")
neighbor_rate_limit = os.getenv("NEIGHBOR_CRAWL_RATE_LIMIT", "30/m")
ssh_sync_rate_limit = os.getenv("SSH_SYNC_TASK_RATE_LIMIT", "120/m")
syslog_rate_limit = os.getenv("SYSLOG_TASK_RATE_LIMIT", "300/m")

celery_conf = dict(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Seoul",
    enable_utc=False,
    # 최신 버전 Celery에서 경고를 없애고 안정적인 재접속을 돕는 옵션
    broker_connection_retry_on_startup=True,
    worker_max_tasks_per_child=int(os.getenv("CELERY_MAX_TASKS_PER_CHILD", "200")),
    worker_send_task_events=True,
    task_send_sent_event=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_transport_options={
        "visibility_timeout": int(os.getenv("CELERY_VISIBILITY_TIMEOUT", "3600")),
    },
    task_default_queue="default",
    task_routes={
        "app.tasks.discovery.run_discovery_job": {"queue": "discovery", "routing_key": "discovery"},
        "app.tasks.neighbor_crawl.run_neighbor_crawl_job": {"queue": "discovery", "routing_key": "discovery"},
        "app.tasks.device_sync.ssh_sync_device": {"queue": "ssh", "routing_key": "ssh"},
        "app.tasks.device_sync.enqueue_ssh_sync_batch": {"queue": "ssh", "routing_key": "ssh"},
        "app.tasks.monitoring.monitor_all_devices": {"queue": "monitoring", "routing_key": "monitoring"},
        "app.tasks.monitoring.collect_gnmi_metrics": {"queue": "monitoring", "routing_key": "monitoring"},
        "app.tasks.smart_alerting.run_dynamic_thresholds": {"queue": "monitoring", "routing_key": "monitoring"},
        "app.tasks.smart_alerting.run_correlations": {"queue": "monitoring", "routing_key": "monitoring"},
        "app.tasks.monitoring.full_ssh_sync_all": {"queue": "monitoring", "routing_key": "monitoring"},
        "app.tasks.maintenance.run_log_retention": {"queue": "maintenance", "routing_key": "maintenance"},
        "app.tasks.compliance.run_scheduled_compliance_scan": {"queue": "maintenance", "routing_key": "maintenance"},
        "app.tasks.compliance.run_scheduled_config_drift_checks": {"queue": "maintenance", "routing_key": "maintenance"},
        "app.tasks.syslog_ingest.ingest_syslog": {"queue": "syslog", "routing_key": "syslog"},
    },
    task_annotations={
        "app.tasks.discovery.run_discovery_job": {"rate_limit": discovery_rate_limit},
        "app.tasks.neighbor_crawl.run_neighbor_crawl_job": {"rate_limit": neighbor_rate_limit},
        "app.tasks.device_sync.ssh_sync_device": {"rate_limit": ssh_sync_rate_limit},
        "app.tasks.syslog_ingest.ingest_syslog": {"rate_limit": syslog_rate_limit},
    },

    beat_schedule={
        # 30초 주기: 전체 장비 상태 및 모니터링 (Ping -> SNMP)
        # NMS 표준 반응성을 위해 30초로 단축하고 단일 태스크로 통합하여 충돌 방지
        "monitor-all-devices-every-30s": {
            "task": "app.tasks.monitoring.monitor_all_devices",
            "schedule": 30.0,
        },
        "collect-gnmi-metrics-every-5s": {
            "task": "app.tasks.monitoring.collect_gnmi_metrics",
            "schedule": float(os.getenv("GNMI_COLLECT_INTERVAL_SEC", "5")),
        },
        "smart-alert-dynamic-thresholds-every-30s": {
            "task": "app.tasks.smart_alerting.run_dynamic_thresholds",
            "schedule": float(os.getenv("SMART_ALERT_DYNAMIC_INTERVAL_SEC", "30")),
        },
        "smart-alert-correlations-every-30s": {
            "task": "app.tasks.smart_alerting.run_correlations",
            "schedule": float(os.getenv("SMART_ALERT_CORRELATION_INTERVAL_SEC", "30")),
        },
        # 1시간 주기: 전체 장비 SSH 상세 동기화 (Config, Neighbors, AP Inventory)
        "full-ssh-sync-every-hour": {
            "task": "app.tasks.monitoring.full_ssh_sync_all",
            "schedule": 3600.0,
        },
        # [NEW] 매일 03:00 - DB 데이터 보존 정책 실행 (오래된 로그 삭제)
        "run-log-retention-daily": {
            "task": "app.tasks.maintenance.run_log_retention",
            "schedule": crontab(hour=3, minute=0),
        },
        "run-config-drift-daily": {
            "task": "app.tasks.compliance.run_scheduled_config_drift_checks",
            "schedule": crontab(hour=3, minute=10),
        },
        "run-compliance-scan-daily": {
            "task": "app.tasks.compliance.run_scheduled_compliance_scan",
            "schedule": crontab(hour=3, minute=30),
        },
    },
)

if Exchange and Queue:
    exchange = Exchange("netmanager", type="direct")
    celery_conf.update(
        task_default_exchange="netmanager",
        task_default_exchange_type="direct",
        task_default_routing_key="default",
        task_queues=(
            Queue("default", exchange, routing_key="default"),
            Queue("discovery", exchange, routing_key="discovery"),
            Queue("ssh", exchange, routing_key="ssh"),
            Queue("monitoring", exchange, routing_key="monitoring"),
            Queue("maintenance", exchange, routing_key="maintenance"),
            Queue("syslog", exchange, routing_key="syslog"),
        ),
    )

celery_app.conf.update(**celery_conf)

if __name__ == '__main__':
    celery_app.start()
