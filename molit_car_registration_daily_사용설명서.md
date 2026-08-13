# 자동차등록현황 일일 적재 사용설명서

## 1. 코드 위치

이 구현은 조장님 reference 폴더와 분리되어 있습니다.

```text
molit_car_registration/
├─ src/
│  ├─ common/          설정·단계 간 계약·구조화 로그
│  ├─ collection/      통계누리 Open API 호출
│  ├─ preprocessing/   원본 정규화·검증·Reject
│  ├─ loading/         JSONL Upsert·Checkpoint·Quota
│  └─ pipelines/       단계 연결 및 실행 진입점
└─ tests/fixtures/     API 없이 실행하는 로컬 fixture
```

조장님이 작업하는 `ref/mlo-01-p1-team3-a/` 폴더는 이 코드의 실행 경로에 포함되지 않습니다.
루트의 `molit_car_registration_daily.py`는 위 폴더의 파이프라인을 호출하는 호환 실행 파일입니다.

## 2. 설계 규칙

- `collection`, `preprocessing`, `loading`은 서로 직접 import하지 않습니다.
- 단계 사이에는 `common.contracts`의 `CollectionEnvelope`, `PreparedBatch` 계약만 전달합니다.
- 외부 설정은 `common.config.Settings`를 통해서만 읽습니다.
- 실행마다 `run_id`를 만들고 구조화 JSONL 로그에 남깁니다.
- 검증 실패 데이터는 Reject 요약으로 기록하고, 원본 전체를 로그에 남기지 않습니다.
- 성공한 기간과 실행 상태는 Checkpoint JSON에 저장합니다.
- 현재 이 분리 버전의 loader는 로컬 JSONL Upsert입니다. SQL/RDS adapter는 loading 단계에 추가할 수 있습니다.

## 3. API 키 설정

PowerShell에서 통계누리 Open API 발급키를 설정합니다.

```powershell
$env:MOLIT_API_KEY = "발급받은_통계누리_API_키"
```

또는 다음 이름도 사용할 수 있습니다.

```powershell
$env:REGISTRATION_API_KEY = "발급받은_통계누리_API_키"
```

키는 Python 파일, JSON 파일, 로그, GitHub에 직접 기록하지 않습니다.

## 4. 실제 API 일일 실행

프로젝트 루트에서 실행합니다.

```powershell
python .\molit_car_registration_daily.py `
  --period 2026-06 `
  --output-dir output
```

`--period`를 생략하면 한국 시간 기준 현재 대상 기간을 사용합니다. API 호출은 한 번의 실행에서 대상 기간 1회만 호출합니다.

## 5. API 없이 fixture로 테스트

```powershell
python .\molit_car_registration_daily.py `
  --fixture .\molit_car_registration\tests\fixtures\registration.json `
  --period 2026-06 `
  --output-dir output `
  --dry-run
```

fixture 실행은 API 키가 없어도 되며, `--dry-run`이면 실제 적재를 하지 않고 수집·전처리 결과만 확인합니다.

## 6. 단계별 동작

```text
통계누리 Open API 또는 fixture
        │
        ▼
collection.registration
  원본 응답 수집 → CollectionEnvelope
        │
        ▼
preprocessing.registration
  시도·시군구·차종·용도·대수 정규화
  잘못된 행은 Reject로 분리 → PreparedBatch
        │
        ▼
loading.registration
  JSONL 자연키 Upsert
  Checkpoint·Quota·구조화 로그 저장
```

JSONL Upsert의 기본 자연키는 다음 다섯 값입니다.

```text
report_month + sido_name + sigungu_name + vehicle_type + usage_type
```

같은 키가 다시 들어오면 새 행을 중복 추가하지 않고 최신 값으로 갱신합니다.

## 7. 생성되는 파일

`--output-dir output`으로 실행하면 다음이 생성됩니다.

```text
output/
├─ vehicle_registration_reports.jsonl  정규화된 자동차등록 데이터
├─ registration_state.json             Checkpoint와 quota 상태
└─ jsonl/                              run_id가 포함된 구조화 로그
```

실행 결과에는 다음 값이 포함됩니다.

- `run_id`: 실행 추적 ID
- `collected_count`: API/fixture에서 받은 원본 행 수
- `preprocessed_count`: 정규화에 성공한 행 수
- `rejected_count`: 검증에서 제외된 행 수
- `inserted_count`, `updated_count`, `unchanged_count`: JSONL Upsert 결과
- `quota_remaining`: 남은 일일 API 호출 횟수

## 8. 문법 검증

```powershell
$py = "C:\Users\Playdata\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$files = Get-ChildItem .\molit_car_registration\src -Recurse -Filter *.py |
  Select-Object -ExpandProperty FullName
& $py -m py_compile .\molit_car_registration_daily.py $files
```
