# 🌐 NetManager: Next-Gen SDN & Automation Platform

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.11-blue.svg)
![React](https://img.shields.io/badge/react-18.0-blue.svg)
![Docker](https://img.shields.io/badge/docker-automated-blue.svg)

**NetManager**는 차세대 네트워크 관리 및 자동화를 위한 웹 기반 SDN 컨트롤러 플랫폼입니다. 복잡한 네트워크 운영을 단순화하고, ZTP(Zero Touch Provisioning), 자동 복구(Auto-Remediation), 그리고 직관적인 Glassmorphism UI를 통해 실시간 가시성을 제공합니다.

## ✨ 주요 기능 (Key Features)

| 모듈 | 기능 설명 |
|------|-----------|
| **🔭 Dashboard** | 실시간 트래픽 모니터링, 장비 상태(Up/Down), 정책 위반 현황 시각화 |
| **🗺️ Topology** | LLDP 기반 네트워크 토폴로지 자동 구성, 계층별(L2/L3) 시각화 |
| **⚡ ZTP** | Zero Touch Provisioning. 신규 장비 연결 시 자동 설정 및 배포 |
| **🛡️ Compliance** | 설정 표준(Golden Config) 위반 감지 및 **자동 복구(Auto-Healing)** |
| **🔄 SWIM** | Software Image Management. 펌웨어 업그레이드 자동화 및 버전 관리 |
| **🔗 Multi-Vendor** | Cisco, Juniper, Arista 등 이기종 벤더 통합 지원 (NAPALM) |
| **🧬 Fabric** | VXLAN/EVPN 패브릭 자동 설정 생성 및 배포 |
| **📡 gNMI** | 차세대 gNMI 텔레메트리 연동을 통한 초고속 데이터 수집 |

---

## 🛠️ 기술 스택 (Tech Stack)

### **Backend**
- **Framework**: FastAPI (Python 3.11) - 고성능 비동기 API
- **Database**: PostgreSQL (Production), SQLite (Dev)
- **Task Queue**: Celery + Redis (비동기 작업 및 스케줄링)
- **Network Libs**: NAPALM, Netmiko, TextFSM, pygnmi

### **Frontend**
- **Library**: React 18 (Vite)
- **Styling**: Tailwind CSS (Glassmorphism Design System)
- **Visualization**: Recharts (차트), React Flow (토폴로지)

---

## 🚀 시작하기 (Quick Start)

**원클릭으로 전체 시스템을 실행하세요.** (Docker Desktop 필요)

### 실행 방법
프로젝트 폴더 내의 실행 스크립트를 더블클릭합니다.

- **`start_server.bat`**: ▶️ 서버 실행 (백그라운드)
- **`stop_server.bat`**: ⏹️ 서버 중지
- **`restart_server.bat`**: 🔄 서버 재시작 (빠름)
- **`update_server.bat`**: 🛠️ **업데이트 적용** (재빌드 후 시작 - 코드 변경 시 사용)

### 수동 실행 (터미널)
```bash
# 전체 서비스 실행 (이미지 변경사항 없음)
docker-compose up -d

# 업데이트 (코드 변경 후 재빌드)
docker-compose up -d --build

# 로그 확인
docker-compose logs -f
```

### 접속 정보
- **Frontend (Web UI)**: http://localhost
- **Backend (API Docs)**: http://localhost:8000/docs
- **Redis**: Port 6379
- **PostgreSQL**: Port 5432

---

## 📂 프로젝트 구조

```
NetManager/
├── Netmanager_Backend/    # FastAPI 백엔드 소스코드
│   ├── app/               # 애플리케이션 로직 (API, Models, Services)
│   ├── firmware_storage/  # 펌웨어 파일 저장소
│   └── templates/         # 설정 템플릿 (Jinja2)
│
├── netmanager-frontend/   # React 프론트엔드 소스코드
│   ├── src/components/    # UI 컴포넌트
│   └── src/pages/         # 페이지 라우트
│
├── certs/                 # SSL 인증서 (HTTPS 적용 시)
├── docker-compose.yml     # Docker 서비스 정의
├── .env                   # 환경 변수 설정
└── *.bat                  # Windows 실행 스크립트
```

## 🔒 보안 및 운영 (Production)
- `.env` 파일에서 비밀번호 및 키 관리
- `certs/` 폴더에 SSL 인증서 추가 시 HTTPS 자동 적용
- 프로덕션 배포 시 `POSTGRES_PASSWORD` 변경 권장

---

**Developed by NetMaster Team**
_Revolutionizing Network Operations with AI & Automation_
