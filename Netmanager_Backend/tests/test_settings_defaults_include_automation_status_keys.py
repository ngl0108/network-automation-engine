from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.api.v1.endpoints import settings as settings_endpoint
from app.models.settings import SystemSetting
from app.models import device as _device
from app.models import credentials as _credentials


def test_settings_defaults_include_auto_discovery_status_keys():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        assert db.query(SystemSetting).count() == 0
        settings_endpoint.get_settings(db=db, current_user=None)
        keys = {s.key for s in db.query(SystemSetting).all()}
        assert "auto_discovery_last_run_at" in keys
        assert "auto_discovery_last_job_id" in keys
        assert "auto_discovery_last_job_cidr" in keys
        assert "auto_discovery_last_error" in keys
        assert "auto_topology_last_run_at" in keys
        assert "auto_topology_last_job_id" in keys
        assert "auto_topology_last_targets" in keys
        assert "auto_topology_last_enqueued_ok" in keys
        assert "auto_topology_last_enqueued_fail" in keys
        assert "auto_topology_last_error" in keys
    finally:
        db.close()
