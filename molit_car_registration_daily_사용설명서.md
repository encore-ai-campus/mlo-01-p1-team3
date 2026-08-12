# 자동차등록현황보고 파이프라인 사용설명서

## 1. 실제 코드 위치

자동차등록 수집기는 조장님이 정한 단계별 구조를 사용합니다.

```text
ref/mlo-01-p1-team3-a/src/
├─ common/
│  ├─ config.py          ← Settings와 환경변수
│  ├─ contracts.py       ← 단계 사이 데이터 계약
│  └─ logging_utils.py   ← 구조화 JSONL 로그
├─ collection/
│  └─ registration.py    ← 통계누리 API 호출
├─ preprocessing/
│  └─ registration.py    ← 원본 행 전처리·검증·Reject
├─ loading/
│  └─ registration.py    ← JSONL/SQL Upsert·상태·Quota
└─ pipelines/
   └─ registration.py    ← Collect → Preprocess → Validate → Load 조합
```

루트의 `molit_car_registration_daily.py`는 기존 실행 명령을 유지하는 wrapper일 뿐이며, 실제 로직은 `src` 아래에 있습니다.

## 2. 핵심 처리 규칙

- `collection`, `preprocessing`, `loading`은 서로 직접 import하지 않습니다.
- 단계 사이에는 `CollectionEnvelope`, `PreparedBatch`, `RejectedRecord` 계약을 사용합니다.
- 환경변수는 `common.config.Settings`를 통해서만 읽습니다.
- 매 실행마다 `run_id`를 만들고 모든 구조화 로그에 포함합니다.
- 실패한 행은 원본 전체를 로그에 남기지 않고 Reject 요약만 남깁니다.
- 실행 상태와 마지막 성공 기간은 Checkpoint JSON에 저장합니다.
- 중고차 관계형 처리·FK 순서·Upsert는 `loading/usedcar.py`에만 둡니다.

## 3. 인증키 설정

PowerShell에서 통계누리 Open API 키를 설정합니다.

```powershell
$env:MOLIT_API_KEY = "발급받은_통계누리_인증키"
```

또는 팀 설정 이름을 사용해도 됩니다.

```powershell
$env:REGISTRATION_API_KEY = "발급받은_통계누리_인증키"
```

키를 Python 파일, JSON, 로그, GitHub에 직접 기록하지 않습니다.

## 4. 로컬 fixture로 실행

실제 API를 호출하지 않고 단계 연결을 검증할 때 사용합니다.

```powershell
cd "ref\mlo-01-p1-team3-a"
$env:PYTHONPATH = "src"
python .\src\pipelines\registration.py `
  --fixture .\tests\fixtures\registration.json `
  --period 2026-06 `
  --sink json
```

저장 없이 수집·전처리·검증만 확인하려면 `--dry-run`을 추가합니다.

```powershell
python .\src\pipelines\registration.py `
  --fixture .\tests\fixtures\registration.json `
  --period 2026-06 `
  --sink json `
  --dry-run
```

## 5. 루트 실행 진입점 사용

기존 명령을 유지해야 할 때는 프로젝트 루트에서 실행합니다.

```powershell
$env:MOLIT_API_KEY = "발급받은_통계누리_인증키"
python .\molit_car_registration_daily.py `
  --period 2026-06 `
  --sink json `
  --output-dir outputs
```

운영 SQL에 적재할 때는 다음처럼 실행합니다.

```powershell
python .\molit_car_registration_daily.py `
  --period 2026-06 `
  --sink sql `
  --output-dir outputs
```

현재 canonical pipeline은 통계누리 정책에 맞춰 실행당 API 호출 1회로 제한합니다. 기간을 지정하지 않으면 `REGISTRATION_START_PERIOD`가 설정된 경우 그 값을 사용하고, 없으면 한국 시간 기준 현재 월을 사용합니다.

## 6. 단계 사이 데이터 흐름

```text
통계누리 API
    ↓
CollectionEnvelope
    ↓
preprocessing.registration
    ├─ 기준월 정규화
    ├─ 시도명·시군구 검증
    ├─ 차량구분·용도구분·수량 분해
    └─ 실패 행 Reject
    ↓
PreparedBatch
    ↓
loading.registration
    ├─ JSONL Upsert
    └─ SQL Upsert
```

하나의 API 원본 행에 `승용>관용`, `승용>자가용` 같은 지표가 여러 개 있으면 전처리 단계에서 지표별 SQL 행으로 펼칩니다.

## 7. 출력과 운영 상태

`--sink json`을 사용하면 다음 파일이 생성됩니다.

```text
outputs/vehicle_registration_reports.jsonl
outputs/registration_state.json
outputs/jsonl
```

- `vehicle_registration_reports.jsonl`: 정규화된 등록 데이터
- `registration_state.json`: 마지막 성공 기간, 실행 상태, quota checkpoint
- `jsonl`: `run_id`, 단계명, 처리 건수, Reject 수, 오류 코드가 포함된 구조화 로그

`--sink sql`은 `vehicle_registration_reports` 테이블에 복합 업무키 기준으로 Upsert합니다.

업무키는 다음 다섯 컬럼입니다.

```text
report_month
sido_name
sigungu_name
vehicle_type
usage_type
```

## 8. 오류와 Reject 확인

실행 결과에는 다음 수치가 포함됩니다.

- `collected_count`: API에서 받은 원본 행 수
- `preprocessed_count`: 전처리된 행 수
- `rejected_count`: 검증 실패 행 수
- `inserted_count`: 새로 저장된 행 수
- `updated_count`: 기존 값이 갱신된 행 수
- `unchanged_count`: 값이 동일한 행 수
- `run_id`: 해당 실행을 추적하는 식별자

실패한 행의 원본 전체와 API 키는 로그에 남기지 않습니다. 로그에는 오류 코드와 식별 가능한 최소 정보만 기록합니다.

## 9. 검증 명령

프로젝트 폴더에서 다음처럼 문법을 확인할 수 있습니다.

```powershell
$py = "C:\Users\Playdata\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$files = Get-ChildItem .\src,.\tests -Recurse -Filter *.py | Select-Object -ExpandProperty FullName
& $py -m py_compile $files
```

`pytest`가 설치된 환경에서는 다음 테스트를 실행합니다.

```powershell
python -m pytest -q
```
