# UI 점검/보완 로그 (NetManager / NetSphere)

## 범위
- 프론트엔드: `netmanager-frontend/src`
- 목표: 정렬/간격/가독성/반응형/호버·포커스/다크·라이트/터치 영역 품질 개선

## 이번 반영 내용(요약)
- 다크/라이트 모드에서 `body` 배경/텍스트가 고정되던 문제를 분리 적용으로 수정
- 포커스 접근성(`:focus-visible`) 아웃라인을 전역으로 추가
- 모바일에서 Sidebar가 화면을 가리던 구조를 Drawer(오버레이)로 변경하고 패딩을 반응형으로 조정
- 전역 `alert()/window.alert()` 제거, Toast 기반 피드백으로 통일
- Sidebar 메뉴에 Notifications/Wireless 추가, Fabric Automation/Images 아이콘 중복 성격 정리

## 체크리스트(중점 항목 1~8)
### 1) UI 요소 정렬/간격
- Desktop(≥1280px): 헤더, 페이지 상단 타이틀, 카드 grid의 좌우 여백 일관성 확인
- Mobile(≤390px): 페이지 `p-6`류가 과도하지 않은지 확인(이번에 주요 페이지는 `p-3 sm:p-4 md:p-6`로 정리)

### 2) 아이콘 중복 표시 제거
- Sidebar 메뉴 아이콘 중복/혼동 요소 확인(Images/Fabric 구분)
- 토폴로지/설정 페이지 등에서 동일 의미의 아이콘이 다른 의미로 재사용되는지 점검

### 3) 텍스트 가독성(크기/대비/줄간격)
- 라이트모드에서 `text-white` 고정 사용 여부 확인(라이선스 카드 텍스트를 라이트/다크 대응으로 정리)
- 작은 텍스트(10~12px)의 대비 부족 여부 확인(특히 dark에서 gray-500 계열)

### 4) 반응형 겹침/깨짐
- Sidebar: 모바일에서 Drawer로 열리고, 오버레이 탭으로 닫히는지 확인
- 헤더: 모바일에서 햄버거 버튼/아이콘이 겹치지 않는지 확인

### 5) Hover/Focus 피드백
- 버튼/링크/입력 필드의 focus-visible 아웃라인 표시 확인
- 주요 버튼(헤더 아이콘/사이드바 메뉴/모달 닫기)의 hover 색상 대비 확인

### 6) 불필요한 여백/패딩 정리
- 페이지별 wrapper 패딩: `p-6`가 모바일에서 과도하면 `p-3 sm:p-4 md:p-6`로 통일 권장
- 모달 내부 스크롤 영역에서 이중 패딩 여부 확인

### 7) 다크/라이트 전환 색상 오류
- `html.dark` / `html.light`에 따라 `body` 배경/텍스트가 올바르게 바뀌는지 확인
- “dark 전용 하드코딩”(`bg-[#0e1012]`, `text-white`)이 라이트에서 읽기 어려운지 점검

### 8) 모바일 터치 영역 최적화
- 헤더 아이콘 버튼: 최소 40px 이상(이번에 `h-10 w-10`로 통일)
- 토글/체크박스: 주변 padding 포함 44px 근접 여부 확인

## 스크린샷 캡처 가이드(수정 전/후)
> 현재 작업 시점에서 “수정 전 UI”의 기준 스냅샷/버전이 저장되어 있지 않아 자동으로 Before를 생성할 수 없습니다.  
> 아래 절차로 “현재(After)” 스냅샷을 먼저 확보하고, 다음부터는 변경 전 캡처를 선행하는 방식으로 운영하는 것을 권장합니다.

### 캡처 권장 뷰포트
- Mobile: 390×844 (iPhone 12/13 Pro 유사)
- Tablet: 768×1024 (iPad 유사)
- Desktop: 1440×900

### 캡처 권장 라우트(대표 화면)
- `/` Dashboard
- `/devices` Device List
- `/devices/:id` Device Detail
- `/topology` Topology(Health/Traffic Flow 토글 포함)
- `/discovery` Auto Discovery
- `/visual-config` Visual Config
- `/config` Config Templates
- `/images` Image Repository
- `/policy` Security Policy
- `/settings` Settings

### Chrome DevTools에서 위치/크기 확인(실측)
1. DevTools 열기 → Elements 탭
2. 대상 요소 선택(Select tool) → Computed에서 `width/height/padding/margin` 확인
3. 모바일 환경: Toggle device toolbar로 뷰포트 변경 후 동일 확인

## 변경 파일(빠른 링크)
- 라이트/다크 body/스크롤/포커스: `netmanager-frontend/src/index.css`
- 모바일 Drawer 사이드바: `netmanager-frontend/src/components/Layout.jsx`
- Sidebar 메뉴/아이콘: `netmanager-frontend/src/components/Sidebar.jsx`
- Toast 통일(여러 페이지): `netmanager-frontend/src/context/ToastContext.jsx` 및 각 페이지 수정

