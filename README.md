# AMEVA Global DB Inspector

---

## 1. 개요 (Abstract)
본 프로젝트는 CPU 기반 극한 엣지 디바이스 환경에서 동작하는 AMEVA 프로젝트 생태계의 비정형/정형 데이터 자원을 통합 검수 및 관리하기 위한 경량 GUI 데이터베이스 관리 파이프라인이다. AI 훈련 파이프라인, 벤치마크 슈트 등 다수의 독립 프로세스에서 동시다발적으로 파생되는 파편화된 SQLite 데이터베이스, VTT 로그, CSV 메타데이터를 단일 인터페이스에서 투명하게 추적, 분석, 보정한다.

특히 무거운 외부 프레임워크(PyQt/PySide 등)에 대한 의존성을 원천 배제하여 DLL 충돌 및 가상환경 파괴를 방지하였으며, DB Lock 메커니즘으로 인한 AI 학습 프로세스의 블로킹 현상을 완전히 억제하는 고정밀 Open-Execute-Close 패턴과 SQLite WAL(Write-Ahead Logging) 최적화를 융합 적용하여 MLOps 인프라의 가용성을 극대화하였다.

---

## 2. 기능 (Features)

### 2.1. 글로벌 워크스페이스 스캐닝 (Dynamic Workspace Telemetry)
본 시스템은 지정된 워크스페이스 상위 디렉토리 아래의 모든 파일 트리를 재귀적으로 순회하여 관리 대상 자원을 자동 식별한다.
- **Target Discovery**: `.db`, `.sqlite`, `.log`, `.csv` 등 유효 데이터 자원을 전수 스캔한다.
- **Ignore Matrix**: `venv`, `.git`, `node_modules`, `__pycache__` 등 비즈니스 로직과 무관한 시스템 디렉토리를 식별 및 즉각 배제(Ignore) 처리하여 스캔 I/O 오버헤드를 원천 억제한다.
- **Hot Swap Support**: 워크스페이스를 실시간으로 스위칭하거나 외부 격리 파일을 직접 마운트(Open)하여 즉시 분석할 수 있다.

### 2.2. DB 브라우저 (Database Browser & Inspector)
활성 DB의 논리적 스키마와 물리적 레코드 상태를 직관적으로 렌더링하고 직접 보정할 수 있는 인터페이스를 제공한다.
- **Schema Profiling**: 활성 DB의 전체 테이블 목록과 내부 컬럼 스펙(데이터 타입, PK 제약조건, NotNull, 기본값)을 사이드바에 즉각 렌더링한다.
- **Data Grid Rendering**: 선택한 테이블의 물리 레코드를 최대 1,000행(Rows)까지 Treeview 그리드 형식으로 한정 로드하여 메모리 맵 한계를 방어한다.
- **CRUD Operations**: 데이터셋 레코드의 삽입(Insert), 수정(Update), 삭제(Delete) 작업을 스크롤 가능한 모달 다이얼로그를 통해 캡슐화하여 제공한다.

### 2.3. 커서 인식 동적 SQL 실행기 (Cursor-Aware Dynamic SQL Executor)
SQL 에디터 탭은 사용자의 입력 커서 위치 및 문맥을 파악하여 쿼리 블록을 동적 분할하고 실행한다.
- **Block Extraction**: 세미콜론(`;`)을 경계로 삼되, 문자열 리터럴 내부의 세미콜론은 무시하는 정규식(Regex) 기반 파서를 가동하여 커서가 위치한 단일 Statement만을 정확히 추출 및 실행(`Ctrl+Enter`)한다. 드래그된 텍스트 영역이 존재할 경우 해당 영역을 최우선 실행한다.
- **Context Protection**: SQL 키워드, 문자열, 주석, 숫자에 대한 실시간 구문 강조(Syntax Highlighting)와 테이블/컬럼명에 대한 인텔리센스 오토컴플리트(Autocomplete) 팝업을 지원하여 수동 입력의 무결성을 확보한다.
- **Word-Level Truncation**: 공백, 언더바(`_`), 특수문자를 경계로 인식하는 단어 단위 삭제(`Ctrl+Delete`, `Ctrl+Backspace`) 커스텀 로직을 구현하여 입력 효율성을 극대화한다.
- **Result Pipelining**: 쿼리별 실행 소요 시간(ms)을 계측하고, `SELECT` 반환 결과 텐서를 DB 브라우저 탭의 데이터 그리드로 자동 파이프(Pipe)하여 즉각 렌더링한다.

### 2.4. 통합 로그 탐색기 (Log Explorer & Live Tail)
파편화된 프로젝트의 `.log` 파일을 통합 스캔하여 단일 뷰어로 병합 추적한다.
- **Semantic Highlighting**: 로드된 텍스트 스트림을 스캔하여 `ERROR`, `WARNING`, `INFO` 등의 위험 인자를 색상 기반으로 자동 분류하고 가시성을 확보한다.
- **Level & Keyword Filtering**: 지정된 로그 레벨(ALL/INFO/WARNING/ERROR)에 따라 라인 뷰를 동적 필터링하며, 키워드 검색 시 매칭 영역을 하이라이트하고 첫 결과로 자동 스크롤한다.
- **Asynchronous Live Tail**: 무거운 스레드 파생 없이 Tkinter 비동기 이벤트 루프 내에서 파일 메타데이터(`stat().st_size`)를 2,000ms 주기로 폴링하여 장기 학습 프로세스의 로깅 스트림을 실시간 갱신한다.

### 2.5. 다중 인코딩 CSV 탐색기 (Multi-Encoding CSV Explorer)
엣지 환경에서 병합되는 이기종 메타데이터(CSV) 파일의 인코딩 충돌을 방어하고 분석 뷰를 제공한다.
- **Encoding Auto-Detection**: `utf-8-sig`, `cp949`, `euc-kr`, `latin-1`의 순차적 디코딩 시도 알고리즘을 통해 텍스트 깨짐 현상을 원천 차단한다.
- **Memory-Bound Grid**: 최대 5,000행(Rows) 로드 제한 메커니즘을 가동하여 시스템 메모리 파괴(OOM)를 방지하며, 컬럼 헤더를 통한 양방향 정렬(Sort)을 지원한다.
- **Client-Side Filtering & Export**: 실시간 행 단위 텍스트 필터링 연산을 지원하며, 현재 표시 중인 정제된 뷰를 완전한 호환성을 지닌 UTF-8-BOM 형식 CSV로 내보내기(Export)할 수 있다.

### 2.6. 상태 텔레메트리 대시보드 (Live Telemetry Dashboard)
- **Matplotlib Integration**: 테이블별 레코드 집계, 최근 30개 쿼리 실행 병목(Execution Timings), 워크스페이스 전역 로그 레벨 분포를 세 가지 실시간 차트로 시각화한다.
- **Auto-Refresh Engine**: 지정된 갱신 주기(2~60초)마다 데이터 상태를 폴링하여 현장 모니터링 체계를 무인 자동화한다. 의존성 패키지 부재 시 텍스트 기반 퀵 스탯 패널로 우회(Fallback) 구동된다.

### 2.7. 극한 엣지 하드웨어 최적화 (Extreme Edge Hardware Optimization)
- **SQLite PRAGMA Injection**: 엣지 디바이스에서 AI 추론 프로세스와 DB 디스크 접근이 충돌할 때 발생하는 I/O 락(Lock) 경쟁을 해소하기 위해, WAL(Write-Ahead Logging) 저널 모드 및 64MB 메모리 맵(Memory Map I/O) 최적화 쿼리를 메뉴 기반으로 일괄 주입한다.

### 2.8. 글로벌 오딧 로깅 체계 (Global Audit Logging)
- **Traceability**: 수행된 모든 CRUD 연산 및 시스템 최적화 PRAGMA 명령어는 물리적 영구 보관소(`logs/db_inspector.log`)에 쿼리 파라미터, 소요 시간(ms), 결과 행수와 함께 전수 기록된다.
- **Log Rotation**: MLOps 로깅 덤프의 비대화를 방지하기 위해 2MB 용량 임계치 초과 시 최대 5개의 파일 인덱스로 자동 순환(Rotating) 백업된다.

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
