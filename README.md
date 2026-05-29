# AMEVA Global DB Inspector

---

## 1. 개요 (Overview)

AMEVA Global DB Inspector는 CPU 기반 극한 엣지 디바이스 환경에서 동작하는 AMEVA 프로젝트 생태계의 데이터를 통합 관리하기 위한 경량 GUI 데이터베이스 관리 툴이다.

엣지 AI 환경에서는 여러 독립 프로세스(STT 학습, 벤치마크, 네트워크 모니터링, 오케스트레이터 등)가 각자의 SQLite 데이터베이스와 로그 파일을 독립적으로 생성한다. 이 도구는 그 파편화된 데이터 자원을 단일 인터페이스에서 검색, 분석, 수정할 수 있도록 설계되었다.

핵심 설계 원칙은 다음 세 가지다.

- **무거운 외부 의존성 배제**: UI는 Python 표준 라이브러리인 Tkinter만 사용한다. PyQt, PySide 등 DLL 의존성 문제를 유발하는 프레임워크는 사용하지 않는다.
- **커넥션 안전성**: 모든 DB 쿼리는 open-execute-close 패턴을 따르며, AI 학습 프로세스가 DB 락(Lock)으로 인해 블로킹되는 상황을 원천적으로 방지한다.
- **동적 환경 적응**: 프로젝트 폴더가 추가되거나 새 DB/로그 파일이 생성될 때, Rescan 기능을 통해 툴을 재시작 없이 즉시 반영할 수 있다.

---

## 2. 기능 (Features)

### 2.1 글로벌 워크스페이스 스캐닝
- 지정된 상위 폴더(워크스페이스) 아래의 모든 `.db`, `.sqlite`, `.log`, `.csv` 파일을 재귀적으로 탐색한다.
- `venv`, `.git`, `node_modules`, `__pycache__` 등 비프로젝트 디렉토리는 자동으로 제외된다.
- 워크스페이스를 언제든지 변경하거나 외부 파일을 직접 열 수 있다.

### 2.2 DB 브라우저 (DB Browser)
- 활성 DB의 테이블 목록, 컬럼 스키마(타입, PK, NotNull, 기본값)를 사이드바에 표시한다.
- 선택한 테이블의 데이터를 최대 1000행까지 그리드 형식으로 렌더링한다.
- INSERT / UPDATE / DELETE 작업을 스크롤 가능한 모달 폼 다이얼로그로 제공한다.

### 2.3 SQL 에디터 (SQL Editor)
- DBeaver 방식의 커서 인식 쿼리 실행: 세미콜론(`;`) 단위로 쿼리 블록을 자동 감지하고 커서가 위치한 블록만 실행한다.
- 드래그 선택 영역이 있을 경우 선택 영역을 우선 실행한다.
- `Ctrl+Enter` 단축키로 즉시 실행한다.
- SQL 키워드(진한 갈색 + 굵게), 문자열 리터럴(초록), 주석(회색 기울임), 숫자(파랑)의 실시간 구문 강조를 지원한다.
- 키워드, 테이블명, 컬럼명에 대한 인텔리센스 자동완성 팝업을 제공한다 (방향키 탐색, Tab/Enter 삽입).
- `Ctrl+Delete` / `Ctrl+Backspace`: 공백, 언더바(`_`), 특수문자 기준 단어 단위 삭제.
- 라인 번호가 좌측에 실시간으로 표시된다.
- 쿼리별 실행 소요 시간(ms)이 툴바에 즉시 표시된다.
- SELECT 결과는 DB 브라우저 탭의 데이터 그리드에 자동으로 파이프된다.

### 2.4 로그 탐색기 (Log Explorer)
- 워크스페이스 전체의 `.log` 파일을 스캔하여 파일 목록, 크기, 수정 일시를 표시한다.
- 파일 내용을 `ERROR` (빨강), `WARNING` (주황), `INFO` (초록), `DEBUG` (회색) 색상으로 구분하여 보여준다.
- 레벨 필터(ALL / INFO / WARNING / ERROR)로 해당 레벨의 라인만 필터링한다.
- 키워드 검색으로 매칭된 부분을 노란색으로 하이라이트하고 첫 결과로 자동 스크롤한다.
- Live Tail 모드: 2초마다 파일 크기를 폴링하여 변경 시 내용을 자동 갱신한다. 장시간 돌아가는 AI 학습 로그를 실시간으로 모니터링할 때 사용한다.

### 2.5 CSV 탐색기 (CSV Explorer)
- 워크스페이스 전체의 `.csv` 파일을 스캔한다.
- `utf-8-sig`, `cp949`, `euc-kr` 등 다중 인코딩을 자동으로 감지하여 한국어 CSV도 올바르게 읽는다.
- 최대 5000행을 Treeview 그리드로 렌더링하며, 컬럼 헤더 클릭으로 오름차순/내림차순 정렬이 가능하다.
- 행 필터: 텍스트 입력으로 현재 로드된 데이터를 클라이언트 사이드에서 즉시 필터링한다.
- 현재 표시 중인 뷰를 UTF-8-BOM CSV로 내보내기(Export)할 수 있다.

### 2.6 라이브 대시보드 (Dashboard)
- matplotlib을 활용한 세 개의 실시간 차트를 제공한다.
  - 테이블별 레코드 수 (막대 그래프)
  - 최근 30개 쿼리 실행 시간 추이 (막대 그래프, 성공/실패 색상 구분)
  - 워크스페이스 전체 로그 레벨 분포 (막대 그래프)
- 퀵 스탯 패널: 활성 DB 경로, 파일 크기, 테이블 수, 마지막 쿼리 결과를 텍스트로 요약한다.
- 자동 갱신(Auto-Refresh) 모드: 2~60초 범위에서 주기를 설정하고 체크박스 하나로 on/off한다.
- matplotlib이 설치되지 않은 환경에서는 퀵 스탯 패널만 표시하고 안내 메시지를 출력한다.

### 2.7 SQLite 최적화
- WAL 저널 모드, 동기화 레벨, 캐시 크기, 메모리 맵 I/O 등을 한 번에 적용하는 최적화 기능을 메뉴에서 제공한다.
- 엣지 디바이스에서 AI 프로세스와 DB 접근이 동시에 발생할 때 발생하는 락 경쟁을 최소화한다.

### 2.8 통합 SQL 쿼리 로깅
- 모든 SQL 실행(CRUD, Raw SQL, 내부 PRAGMA 포함)이 `logs/db_inspector.log`에 자동 기록된다.
- 로그 항목은 타임스탬프, 레벨, 대상 DB명, 쿼리 원문, 파라미터, 성공/실패, 결과 행수, 실행 시간(ms)을 포함한다.
- 파일 크기가 2MB를 초과하면 최대 5개의 백업 파일로 자동 롤오버(Rotating)된다.

---

## 3. 프로젝트 구조 (Project Structure)

```
AMEVA-Database/
├── run.py                      # 실행 진입점 (Entry Point)
├── requirements.txt            # Python 의존성 목록
├── README.md                   # 이 문서
├── logs/
│   └── db_inspector.log        # 자동 생성되는 SQL 쿼리 로그
└── tools/
    ├── __init__.py             # 패키지 메타데이터
    ├── workspace_scanner.py    # 워크스페이스 파일 스캔 엔진
    ├── db_manager.py           # DB 연결, 쿼리 실행, 로깅 엔진
    ├── autocomplete.py         # SQL 자동완성 팝업 위젯
    ├── syntax_highlighter.py   # SQL 구문 강조 엔진
    ├── db_browser_tab.py       # DB 브라우저 탭 (스키마, 데이터 그리드, CRUD)
    ├── sql_editor_tab.py       # SQL 에디터 탭 (실행, 자동완성, 강조)
    ├── log_explorer_tab.py     # 로그 탐색기 탭 (검색, 필터, Live Tail)
    ├── csv_explorer_tab.py     # CSV 탐색기 탭 (정렬, 필터, 내보내기)
    ├── dashboard_tab.py        # 라이브 대시보드 탭 (차트, 자동 갱신)
    └── app.py                  # 메인 앱 오케스트레이터
```

---

## 4. 코드 설명 (Code Architecture)

### 4.1 계층 구조

```
run.py
 └── AMEVAInspectorApp  (tools/app.py)
      ├── WorkspaceScanner  (tools/workspace_scanner.py)
      │    └── 워크스페이스 파일 탐색 — DB, Log, CSV
      ├── DBManager  (tools/db_manager.py)
      │    ├── QueryRecord  — 쿼리 실행 결과 불변 레코드
      │    └── query_history deque — 대시보드 차트용 인메모리 히스토리
      ├── DBBrowserTab  (tools/db_browser_tab.py)
      │    └── CRUDDialog  — INSERT/UPDATE 모달 폼
      ├── SQLEditorTab  (tools/sql_editor_tab.py)
      │    ├── AutocompletePopup  (tools/autocomplete.py)
      │    └── SyntaxHighlighter  (tools/syntax_highlighter.py)
      ├── LogExplorerTab  (tools/log_explorer_tab.py)
      ├── CSVExplorerTab  (tools/csv_explorer_tab.py)
      └── DashboardTab  (tools/dashboard_tab.py)
```

### 4.2 이벤트 전파 패턴

`AMEVAInspectorApp`는 DB 전환이나 워크스페이스 변경이 발생할 때 등록된 모든 탭에 `on_db_changed()` 또는 `on_workspace_changed()`를 호출한다. 각 탭은 이 콜백을 구현하여 자신의 상태를 갱신한다. 탭 간 직접 의존관계는 없으며, 앱 계층이 중재자(Mediator) 역할을 한다.

### 4.3 DBManager — 커넥션 안전성

모든 DB 접근은 `execute()` 메서드 하나를 통해 이루어지며, 매 호출마다 연결을 열고 쿼리를 실행하고 닫는 open-execute-close 패턴을 엄격히 따른다. `finally` 블록에서 `conn.close()`를 보장하므로 예외 발생 시에도 DB 파일 락이 유지되지 않는다.

### 4.4 SQL 실행 우선순위

SQL 에디터의 `_get_statement_at_cursor()` 메서드는 다음 우선순위로 실행할 쿼리를 결정한다.

1. **선택 영역**: 마우스 드래그로 텍스트가 선택된 경우 선택된 부분만 실행한다.
2. **커서 위치 블록**: 세미콜론 구분자를 파싱하여 커서가 위치한 쿼리 블록을 추출한다. 문자열 리터럴 내의 세미콜론은 구분자로 인식하지 않는다.
3. **전체 내용**: 세미콜론이 없는 단일 쿼리의 경우 전체 에디터 내용을 실행한다.

---

## 5. 설치 및 실행 (Installation & Usage)

### 5.1 의존성 설치

```powershell
# 워크스페이스 내 다른 프로젝트의 Python 환경을 활용하는 경우
..\AMEVA-STT-Trainer\venv\Scripts\pip.exe install -r requirements.txt

# 시스템 Python을 사용하는 경우
pip install -r requirements.txt
```

> Tkinter는 Python 표준 라이브러리에 포함되므로 별도 설치가 필요 없다.
> matplotlib은 Dashboard 차트 기능에만 필요하다. 미설치 시 DB Browser, SQL Editor, Log/CSV Explorer는 정상 동작한다.

### 5.2 실행

```powershell
# AMEVA-Database 폴더 기준
python run.py

# 다른 프로젝트의 Python 환경 사용
..\AMEVA-STT-Trainer\venv\Scripts\python.exe run.py
```

### 5.3 단축키 요약

| 단축키              | 동작                          |
|---------------------|-------------------------------|
| `Ctrl + Enter`      | 커서 위치 SQL 블록 실행       |
| `Ctrl + Delete`     | 앞 단어 삭제 (공백/언더바 기준)|
| `Ctrl + Backspace`  | 뒤 단어 삭제 (공백/언더바 기준)|
| `Tab` / `Enter`     | 자동완성 팝업 선택 삽입       |
| `Esc`               | 자동완성 팝업 닫기            |
| 방향키 위/아래      | 자동완성 팝업 탐색            |

---

## 6. 데이터베이스 관리 가이드 (DB Management Guide)

### 6.1 다중 프로젝트 DB 전환

툴 실행 시 상위 워크스페이스 폴더(`small_prj`)를 자동으로 스캔하여 발견된 모든 `.db` 파일을 드롭다운 목록에 채운다. 목록에서 DB를 선택하면 DB Browser, SQL Editor의 자동완성 캐시, Dashboard 차트가 모두 즉시 전환된다.

### 6.2 SQLite 최적화 적용 시점

AI 학습 프로세스(`AMEVA-STT-Trainer`)와 Inspector 툴이 동시에 같은 DB에 접근하는 경우, 반드시 메뉴 > Tools > "Optimize SQLite" 를 실행하여 WAL 모드를 활성화할 것을 권장한다. WAL(Write-Ahead Logging) 모드는 쓰기 프로세스가 진행되는 동안 읽기 프로세스를 블로킹하지 않아 AI 추론 루프의 지연을 방지한다.

### 6.3 대용량 테이블 조회 전략

- DB Browser는 기본적으로 `LIMIT 1000`을 적용한다.
- 특정 조건의 데이터가 필요할 경우 SQL 에디터에서 직접 `WHERE` 조건과 `LIMIT`을 조합하여 조회하고, 결과는 자동으로 DB Browser 그리드에 표시된다.

---

## 7. 로그 및 CSV 분석 가이드 (Log & CSV Analysis)

### 7.1 분산 로그의 통합 조회

AMEVA 생태계에서 발견된 주요 로그 파일 유형은 다음과 같다.

| 경로 패턴                                          | 내용                        |
|----------------------------------------------------|-----------------------------|
| `AMEVA-STT-Trainer/logs/task_*.log`                | 학습/데이터셋 빌드 태스크 Stdout |
| `AMEVA-Benchmark-Suite/AMEVA_Setup_Report.log`     | 싱귤래리티 배포 리포트      |
| `AMEVA-Database/logs/db_inspector.log`             | Inspector SQL 쿼리 이력     |
| `networkChanger/db/network_log.csv`                | 네트워크 상태 변화 로그     |
| `voice/ameva_result_*.csv`                         | STT 추론 결과 및 화자 분리  |

Log Explorer 탭의 레벨 필터를 `ERROR`로 설정하면 모든 프로젝트의 오류 라인만 빠르게 추려볼 수 있다.

### 7.2 한국어 CSV 인코딩 처리

`networkChanger`의 CSV와 일부 벤치마크 보고서는 CP949 또는 EUC-KR로 인코딩되어 있다. CSV Explorer는 `utf-8-sig` → `utf-8` → `cp949` → `euc-kr` → `latin-1` 순서로 인코딩을 자동 감지하여 깨짐 없이 표시한다.

---

## 8. 성능 및 최적화 노트 (Performance Notes)

### 8.1 CPU 엣지 환경에서의 주의사항

- Dashboard의 Auto-Refresh 기능을 AI 추론 루프와 동시에 사용할 때는 갱신 주기를 10초 이상으로 설정하여 CPU 경쟁을 최소화할 것을 권장한다.
- Log Explorer의 Live Tail은 파일 크기 비교(`stat().st_size`)만 수행하므로 파일 I/O 오버헤드가 극히 낮다.
- 대용량 CSV(22MB 이상의 metadata.csv 등)는 최대 5000행만 로드된다. 전체 데이터 분석이 필요한 경우 SQL 에디터에서 해당 데이터를 DB에 임포트한 뒤 쿼리로 분석하는 방식을 권장한다.

### 8.2 쿼리 성능 진단

SQL 에디터 실행 후 우측 상단에 표시되는 `Last: X ms`를 통해 쿼리 성능을 즉시 확인할 수 있다. 100ms를 초과하는 쿼리는 인덱스 생성 또는 쿼리 재작성을 검토해야 한다.

Dashboard > Query Timings 차트에서 지속적으로 높은 실행 시간을 보이는 쿼리 패턴을 시각적으로 식별할 수 있다.

---

## Contributors

| 이름            | 역할                                                     |
|-----------------|----------------------------------------------------------|
| AMEVA Project   | 프로젝트 설계, CPU 엣지 AI 아키텍처 정의                 |
| Antigravity AI  | 코드 구현, 모듈 설계, 문서 작성                          |
