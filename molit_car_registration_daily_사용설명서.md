# 통계누리 자동차등록대수현황 시도별 수집기 사용설명서

## 1. 프로그램 목적

`molit_car_registration_daily.py`는 국토교통부 통계누리의 공식 Open API를 하루 한 번 호출해 `자동차등록대수현황 시도별` 월별 자료를 누적 저장하는 프로그램입니다.

공식 API 요청 주소는 다음과 같습니다.

```text
https://stat.molit.go.kr/portal/openapi/service/rest/getList.do
```

현재 대상 통계표 설정은 다음과 같습니다.

| 항목 | 값 |
|---|---:|
| `form_id` | `5498` |
| `style_num` | `2` |
| 자료 주기 | 월별 |
| 인증 방식 | 통계누리 Open API 인증키 |

공식 API는 `key`, `form_id`, `style_num`, `start_dt`, `end_dt`를 요청 인자로 사용합니다. 자세한 내용은 [통계누리 API 목록](https://stat.molit.go.kr/portal/api/apiList.do)을 참고하세요.

## 2. 필요한 파일

실행에 필요한 파일은 다음 하나입니다.

```text
molit_car_registration_daily.py
```

기존의 `molit_car_registration_crawler.py`에는 의존하지 않습니다.

## 3. 인증키 설정

인증키를 코드에 직접 입력하지 않고 `MOLIT_API_KEY` 환경변수로 설정합니다.

PowerShell에서 현재 창에만 설정하려면 다음과 같이 입력합니다.

```powershell
$env:MOLIT_API_KEY = "발급받은_통계누리_인증키"
```

설정 여부는 키 전체를 출력하지 않고 다음처럼 확인할 수 있습니다.

```powershell
if ($env:MOLIT_API_KEY) { "API 키 설정됨" } else { "API 키 없음" }
```

새 PowerShell 창이나 작업 스케줄러에서도 사용하려면 Windows 사용자 환경변수로 등록해야 합니다.

```powershell
[Environment]::SetEnvironmentVariable(
    "MOLIT_API_KEY",
    "발급받은_통계누리_인증키",
    "User"
)
```

환경변수 등록 후에는 새 PowerShell 창을 열어야 반영됩니다.

## 4. 기본 실행 방법

프로젝트 폴더에서 다음 명령을 실행합니다.

```powershell
cd "C:\Users\Playdata\Documents\ChatGPT\프로젝트 1"
python .\molit_car_registration_daily.py --output-dir outputs
```

현재 Python 환경에서 SSL 인증서 오류가 발생할 때만 다음처럼 `--insecure`를 추가합니다.

```powershell
python .\molit_car_registration_daily.py --output-dir outputs --insecure
```

`--insecure`는 HTTPS 인증서 검증을 끄는 옵션이므로 운영 환경에서는 사용하지 않는 것이 좋습니다.

## 5. 실행 흐름

프로그램은 실행할 때 다음 순서로 동작합니다.

1. 현재 월부터 과거 방향으로 최대 25개월을 조회합니다.
2. 자료가 존재하는 가장 최근 월을 최신 월로 판단합니다.
3. 기존 누적 CSV가 없으면 최신 월 자료부터 저장합니다.
4. 기존 자료보다 최신 월이 있으면 누락된 월을 모두 받아 최신 월이 위로 오도록 합칩니다.
5. 새 월 자료가 없으면 기존 최저 월의 직전 월을 받아 아래쪽에 추가합니다.
6. 같은 기준월·지역 행이 다시 들어오면 기존 값을 최신 API 응답으로 갱신합니다.
7. 최종 결과를 기준월 내림차순으로 정렬해 CSV에 다시 씁니다.

예를 들어 기존 자료가 다음과 같다고 가정합니다.

```text
2026-06
2026-05
2026-04
```

### 새 월 자료가 있는 경우

API에 `2026-07` 자료가 새로 올라오면 다음처럼 됩니다.

```text
2026-07  ← 최신 자료
2026-06
2026-05
2026-04
```

### 새 월 자료가 없는 경우

새로운 `2026-07` 자료가 없으면 `2026-03`을 조회해 다음처럼 추가합니다.

```text
2026-06  ← 최신 자료
2026-05
2026-04
2026-03  ← 이전 자료 추가
```

## 6. 결과 파일

기본적으로 `outputs` 폴더에 다음 파일이 생성됩니다.

### 누적 데이터

```text
outputs\자동차등록대수현황_시도별_누적.csv
```

UTF-8 BOM 형식의 CSV 파일이며 Excel에서 바로 열 수 있습니다. 첫 번째 컬럼은 `기준월`이고, 이후 API가 반환하는 지역·통계 항목 컬럼이 이어집니다.

### 실행 상태

```text
outputs\자동차등록대수현황_시도별_누적_상태.json
```

실행 상태 파일에는 다음 정보가 저장됩니다.

- 최근 실행 시각
- 최신 월 탐색 대상 월
- 실제로 받아온 월
- 이번 실행 동작(`initial_latest`, `append_new_latest`, `backfill_previous`)
- 누적 행 수
- 누적 자료의 최저·최고 월
- `form_id`, `style_num`, API 주소

인증키 자체는 상태 파일에 저장하지 않습니다.

## 7. 주요 명령 옵션

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--output-dir` | `outputs` | 결과 저장 폴더 |
| `--max-lookback` | `24` | 최신 월 검색 시 과거로 확인할 최대 개월 수 |
| `--insecure` | 미사용 | SSL 인증서 검증 생략 |

예시:

```powershell
python .\molit_car_registration_daily.py `
    --output-dir .\outputs `
    --max-lookback 36
```

## 8. 오류 대응

### `MOLIT_API_KEY 환경변수 ... 설정하세요`

현재 PowerShell에 키가 설정되지 않은 상태입니다.

```powershell
$env:MOLIT_API_KEY = "발급받은_인증키"
```

### `CERTIFICATE_VERIFY_FAILED`

Python이 통계누리 서버의 인증서 체인을 신뢰하지 못하는 오류입니다. 우선 확인용으로만 다음 명령을 사용할 수 있습니다.

```powershell
python .\molit_car_registration_daily.py --output-dir outputs --insecure
```

### `HTTP Error 500`

통계누리는 아직 공개되지 않은 미래 월을 정상적인 `INFO-200` 대신 HTTP 500으로 반환하는 경우가 있습니다. 프로그램은 이 응답을 자료 없음으로 처리하고 이전 월을 계속 탐색합니다.

모든 월에서 계속 실패하면 다음을 확인합니다.

- 인증키가 유효한지
- 인증키가 해당 Open API 사용 승인을 받았는지
- `form_id=5498`, `style_num=2`가 현재 제공 중인지
- 통계누리 서버 상태에 문제가 없는지

### `INFO-100`

인증키가 유효하지 않습니다. 키를 재발급받아 환경변수를 다시 설정합니다.

### `INFO-200`

해당 월의 자료가 없습니다. 최신 월을 찾는 과정에서는 정상적인 응답입니다.

### `INFO-300`

해당 통계표 Open API 서비스가 개방 취소 상태입니다. 통계누리 API 목록에서 현재 제공 여부를 확인해야 합니다.

## 9. 하루 한 번 자동 실행

Windows 작업 스케줄러에 등록할 때는 다음 항목을 사용합니다.

### 프로그램

```text
python
```

### 인수

```text
C:\Users\Playdata\Documents\ChatGPT\프로젝트 1\molit_car_registration_daily.py --output-dir "C:\Users\Playdata\Documents\ChatGPT\프로젝트 1\outputs"
```

### 시작 위치

```text
C:\Users\Playdata\Documents\ChatGPT\프로젝트 1
```

트리거는 `매일 1회`로 설정합니다. 작업 스케줄러가 실행하는 계정에 `MOLIT_API_KEY` 사용자 환경변수가 등록되어 있어야 합니다.

## 10. 운영 시 주의사항

- API 키를 Python 파일, CSV, JSON, Git 저장소에 직접 기록하지 않습니다.
- API 키가 외부에 노출되면 통계누리에서 해당 키를 폐기하고 재발급합니다.
- 공식 API를 과도하게 반복 호출하지 않습니다.
- `--insecure`는 임시 확인용으로만 사용합니다.
- 누적 CSV를 삭제하면 다음 실행 시 최신 월부터 다시 시작합니다.

## 11. 코드 구조

수집기 코드는 기능별 모듈로 나누어져 있습니다.

```text
molit_car_registration_daily.py  ← 기존 실행 명령을 유지하는 진입점
molit_car_registration/
├─ config.py       ← API 주소, 통계표 ID, 환경변수 설정
├─ periods.py      ← 월 검증과 월 이동 계산
├─ api_client.py   ← 통계누리 Open API 호출과 응답 파싱
├─ storage.py      ← CSV 읽기, 중복 제거, 병합, 저장
├─ collector.py    ← 최신 월 탐색과 일일 적재 흐름
├─ cli.py          ← 명령줄 옵션과 오류 메시지
└─ __main__.py     ← python -m molit_car_registration 실행 지원
```

기존 실행 방식은 바뀌지 않았습니다.

```powershell
python .\molit_car_registration_daily.py --output-dir outputs --insecure
```

모듈 실행 방식도 사용할 수 있습니다.

```powershell
python -m molit_car_registration --output-dir outputs --insecure
```
