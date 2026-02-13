# NetManager API 프로젝트 구조
netmanager/
├── README.md # 프로젝트 설명 (현재 파일)
├── requirements.txt # Python 패키지 의존성
├── main.py # FastAPI 애플리케이션 진입점
├── celery_app.py # Celery 비동기 작업 설정
├── populate_db.py # 테스트 데이터 생성 스크립트
│
├── app/ # 주요 애플리케이션 모듈
│ ├── init.py
│ ├── main.py # FastAPI 앱 설정 및 라이프사이클
│ ├── celery_app.py # Celery 인스턴스
│ │
│ ├── db/ # 데이터베이스 레이어
│ │ ├── init.py
│ │ ├── session.py # SQLAlchemy 세션 관리
│ │ └── base.py # Base 모델 클래스
│ │
│ ├── models/ # 데이터베이스 모델
│ │ ├── init.py
│ │ └── device.py # 통합된 모든 모델 (Device, Interface, Site 등)
│ │
│ ├── schemas/ # Pydantic 스키마
│ │ ├── init.py
│ │ └── device.py # 모든 API 응답/요청 스키마
│ │
│ ├── api/ # API 엔드포인트
│ │ └── v1/ # API 버전 1
│ │ ├── init.py
│ │ ├── router.py # 라우터 통합 설정
│ │ └── endpoints/ # 각 엔드포인트 구현
│ │ ├── init.py
│ │ ├── devices.py # 장비 관리 API
│ │ ├── config.py # 설정 관리 API
│ │ ├── logs.py # 로그 조회 API
│ │ ├── config_template.py # 템플릿 관리 API
│ │ └── misc.py # SDN 기능 API
│ │
│ ├── tasks/ # Celery 비동기 작업
│ │ ├── init.py
│ │ ├── monitoring.py # ✅ 장비 모니터링 태스크 (추가됨)
│ │ └── config.py # 설정 배포 태스크
│ │
│ └── core/ # 핵심 비즈니스 로직
│ ├── init.py
│ ├── ssh_service.py # SSH 연결 관리
│ ├── snmp_service.py # SNMP 모니터링
│ ├── syslog_service.py # Syslog 수집 서비스
│ └── parser_service.py # Cisco 설정 파서
│
├── tests/ # 테스트 코드
│ ├── init.py
│ ├── test_api.py
│ ├── test_models.py
│ └── conftest.py
│
├── data/ # 데이터 저장소
│ ├── backups/ # 설정 백업 파일
│ ├── logs/ # 애플리케이션 로그
│ └── netmanager.db # SQLite 데이터베이스
│
└── docs/ # 프로젝트 문서
├── api.md
├── architecture.md
└── deployment.md

text

## 주요 파일 상세 설명

### **루트 디렉토리**
- `main.py` - FastAPI 애플리케이션 진입점 및 CORS 설정
- `celery_app.py` - Celery 비동기 작업 설정 (Redis 브로커, 스케줄링)
- `requirements.txt` - FastAPI, SQLAlchemy, Netmiko, Celery 등 패키지 의존성
- `populate_db.py` - SDN 모의 데이터 생성 스크립트

### **app/tasks/monitoring.py** - 장비 모니터링 태스크
```python
@shared_task
def monitor_all_devices():
    """
    Celery 비동기 작업: 모든 장비의 상태를 SNMP로 모니터링
    - 장비 상태 확인 (online/offline)
    - CPU/메모리 사용률 수집
    - DB에 상태 업데이트
    """
app/core/ - 핵심 서비스 모듈
ssh_service.py - Netmiko 기반 SSH 연결 및 설정 관리

snmp_service.py - PySNMP 기반 장비 상태 모니터링

syslog_service.py - Syslog 메시지 수집 서버

parser_service.py - Cisco 설정 파싱 및 검증

app/models/device.py - 통합 데이터 모델
python
# 주요 모델 클래스:
# - Site (사이트 계층 구조)
# - Device, Interface, Link (장비 관리)
# - Policy, FirmwareImage (SDN 기능)
# - SystemMetric, EventLog (모니터링)
# - ConfigTemplate, ConfigBackup (설정 관리)
API 엔드포인트 요약
경로	기능	메서드
/api/v1/devices/	장비 목록 조회/등록	GET, POST
/api/v1/devices/{id}	장비 상세 조회	GET
/api/v1/devices/topology/links	토폴로지 링크 조회	GET
/api/v1/config/pull/{device_id}	설정 백업 수집	POST
/api/v1/logs/	이벤트 로그 조회	GET
/api/v1/templates/	설정 템플릿 관리	GET, POST, PUT, DELETE
/api/v1/sdn/sites	사이트 계층 조회	GET
/api/v1/sdn/policies	네트워크 정책 조회	GET
Celery 비동기 작업
monitor_all_devices: 60초마다 실행되는 장비 상태 모니터링

pull_and_parse_config: 장비 설정 백업 수집

deploy_config_task: 템플릿 기반 설정 배포

시작 방법
bash
# 의존성 설치
pip install -r requirements.txt

# 데이터베이스 초기화 및 테스트 데이터 생성
python populate_db.py

# FastAPI 서버 시작
python main.py

# Celery 워커 시작 (별도 터미널)
celery -A app.celery_app worker --loglevel=info

# Celery Beat 시작 (스케줄러, 별도 터미널)
celery -A app.celery_app beat --loglevel=info
이 구조는 Cisco 네트워크 장비를 관리하는 완전한 SDN(Software Defined Networking) 스타일의 관리 시스템을 구현하고 있습니다.

text

이렇게 업데이트된 구조도에 `monitoring.py` 파일이 명확히 포함되었습니다. `monitoring.py`는 Celery의 정기 작업으로 장비 상태를 SNMP를 통해 모니터링하는 핵심 기능을 담당합니다.