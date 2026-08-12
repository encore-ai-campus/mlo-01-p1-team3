# 우리 자동차등록 수집기

이 폴더는 조장님 reference 폴더와 분리된 자동차등록 전용 구현입니다.

```text
molit_car_registration/
├─ src/
│  ├─ common/          설정·계약·로그
│  ├─ collection/      통계누리 API 호출
│  ├─ preprocessing/   원본 전처리·Reject
│  ├─ loading/         JSONL 저장·Checkpoint·Quota
│  └─ pipelines/       전체 실행 흐름
└─ tests/fixtures/     로컬 fixture
```

루트에서 실행:

```powershell
$env:MOLIT_API_KEY = "발급받은_키"
python .\molit_car_registration_daily.py --period 2026-06 --output-dir output
```

API 없이 fixture로 확인:

```powershell
python .\molit_car_registration_daily.py `
  --fixture .\molit_car_registration\tests\fixtures\registration.json `
  --period 2026-06 `
  --output-dir output `
  --dry-run
```
