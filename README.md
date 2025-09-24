\# Standard Network Config Manager



Cisco 네트워크 장비(Switch, Router, WLC)의 구성을 GUI를 통해 표준화하고 일관되게 관리할 수 있는 데스크톱 애플리케이션입니다. 사용자가 GUI에서 설정값을 입력하면 자동으로 Ansible 플레이북을 생성하여 구성 배포를 자동화합니다.



\## 🎯 프로젝트 비전



\- \*\*표준화된 구성 관리\*\*: CLI 전문 지식 없이도 네트워크 엔지니어가 직관적으로 사용 가능

\- \*\*다중 OS 지원\*\*: IOS-XE, NX-OS 등 다양한 Cisco OS 유형별 맞춤 구성

\- \*\*자동화된 배포\*\*: GUI 입력을 통한 Ansible 플레이북 동적 생성 및 실행

\- \*\*인적 오류 최소화\*\*: 표준 구성 정책의 일관된 적용으로 네트워크 안정성 극대화



\## 🏗️ 아키텍처



프로젝트는 \*\*관심사 분리(Separation of Concerns)\*\* 원칙에 따라 3계층으로 설계되었습니다:



\### 📱 UI 계층 (View)

\- \*\*PySide6\*\* 기반 다중 탭 인터페이스

\- 표준 구성 문서의 모듈 계층 구조를 반영한 직관적 UI

\- 모든 사용자 입력을 구조화된 데이터로 수집



\### 🧠 핵심 로직 계층 (Controller \& Model)

\- OS 유형별 조건부 로직을 통한 지능적 플레이북 생성

\- 모듈별 헬퍼 함수를 통한 체계적인 구성 관리

\- 표준 문서 기반의 전문가 지식 적용



\### ⚙️ 실행 계층 (Execution Engine)

\- 현재: Windows 개발 환경용 Mock 엔진

\- 향후: ansible-runner 기반 실제 실행 엔진



\## 📁 프로젝트 구조



```

ansible\_config\_editor/

├── main.py                     # 애플리케이션 진입점

├── ui/

│   ├── main\_window.py         # 메인 GUI 인터페이스 (핵심 개발 영역)

│   └── playbook\_view.py       # 플레이북 미리보기 UI (준비 중)

├── core/

│   ├── playbook\_manager.py    # 플레이북 생성 로직 (핵심 개발 영역)

│   └── ansible\_engine.py      # Mock 실행 엔진 (현재 유지)

├── ansible/

│   ├── inventory/             # 장비 목록 정의

│   └── playbooks/            # 참고용 정적 플레이북

├── requirements.txt           # Python 패키지 의존성

└── README.md                 # 이 파일

```



\## 🚀 현재 개발 상태



\### ✅ 완료된 기능

\- PySide6 기반 기본 GUI 프레임워크 구축

\- 3계층 아키텍처 기본 구조 수립

\- OS 유형 선택 기능

\- 장비 관리 (추가/제거) 기능

\- Global 모듈 기본 UI (Hostname, Logging, NTP, AAA)

\- Mock 실행 엔진을 통한 개발 환경 피드백



\### 🔄 개발 중

\- Interface 모듈 상세 구현

\- VLAN 모듈 상세 구현

\- Routing 모듈 상세 구현

\- HA (고가용성) 모듈 상세 구현

\- Security 모듈 완성



\### 📋 계획된 기능

\- 구성 저장/불러오기

\- 입력 유효성 검사

\- 실제 Ansible 엔진 연동

\- 실행 전 미리보기 (Dry-Run)

\- 상세 로깅 및 이력 관리



\## 🛠️ 개발 환경 설정



\### 필요 조건

\- Python 3.8+

\- PySide6

\- PyYAML



\### 설치 및 실행

```bash

\# 의존성 설치

pip install -r requirements.txt



\# 애플리케이션 실행

python main.py

```



\## 📋 개발 로드맵



\### 1단계: 핵심 모듈 상세 구현 (현재 ~ 3개월)

\- \*\*Interface 모듈\*\*: 물리 인터페이스, Port-Channel, SVI 설정 UI

\- \*\*VLAN 모듈\*\*: VLAN 관리 및 SVI 상세 설정

\- \*\*Routing 모듈\*\*: Static, OSPF, BGP 프로토콜별 탭

\- \*\*HA 모듈\*\*: OS별 StackWise Virtual/vPC 조건부 UI



\### 2단계: 고급 기능 및 편의성 향상 (3 ~ 6개월)

\- 구성 저장 및 불러오기 (.yaml/.json 프로젝트 파일)

\- 변수 관리 시스템 (사이트 코드, 건물, 층 등)

\- 실시간 입력 유효성 검사

\- 기존 장비 구성 가져오기 (ios\_facts 활용)



\### 3단계: 실제 배포 및 운영 준비 (6개월 이후)

\- ansible-runner 기반 실제 실행 엔진

\- Dry-run 미리보기 기능

\- 상세 로깅 및 감사 추적

\- PyInstaller를 통한 단일 실행 파일 패키징



\## 💡 주요 설계 특징



\### 표준 문서 기반 설계

\- CSV 파싱이 아닌 전문가의 업무 흐름과 지식을 \*\*설계 청사진\*\*으로 활용

\- 모듈 → 서브모듈 계층 구조를 UI와 로직에 직접 반영



\### OS별 맞춤 구성

```python

\# 예시: OS 유형에 따른 조건부 명령어 생성

if "IOS-XE" in os\_type:

&nbsp;   commands.append("vrf forwarding Mgmt-intf")

elif "NX-OS" in os\_type:

&nbsp;   commands.append("feature lacp")

&nbsp;   commands.append("vrf member management")

```



\### Windows 개발 친화적

\- Mock 엔진을 통해 실제 Linux/Ansible 환경 없이도 개발 가능

\- 플레이북 생성 결과를 즉시 GUI에서 확인 가능



\## 🔧 현재 주요 이슈



\### main\_window.py의 수정 필요 사항

```python

\# 라인 30: OS 타입 리스트가 빈 상태

self.combo\_os\_type.addItems()  # ← 수정 필요



\# 라인 70, 74: 헤더 라벨이 누락

self.logging\_table.setHorizontalHeaderLabels()  # ← 수정 필요

self.ntp\_table.setHorizontalHeaderLabels()      # ← 수정 필요



\# 라인 176, 184: 빈 리스트 초기화

log\_hosts =''  # ← \[] 로 수정 필요

ntp\_servers =''  # ← \[] 로 수정 필요

```



\## 🤝 기여 방법



1\. \*\*핵심 개발 영역\*\*: `ui/main\_window.py`와 `core/playbook\_manager.py` 집중

2\. \*\*표준 문서 참조\*\*: 구현 시 제공된 표준 구성 문서의 계층 구조 반영

3\. \*\*테스트\*\*: Mock 엔진을 통한 플레이북 생성 결과 확인



\## 📞 문의



프로젝트 관련 문의사항이나 개발 방향에 대한 논의가 필요한 경우 이슈를 등록해 주세요.



---



\*\*목표\*\*: CLI 전문 지식 없이도 네트워크 엔지니어가 직관적으로 사용할 수 있는 \*\*전문적이고 안정적인\*\* Cisco 네트워크 구성 자동화 플랫폼 구축

