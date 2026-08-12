# Source Registry — MVP

- document_id: SRC-MLO-001
- version: v1
- document_state: Review
- baseline_date: <TODO: YYYY-MM-DD>
- provenance: 사용자 제공 Source 주소와 ref 수집기 참고
- owner_role: <TODO>
- reviewer_roles: [<TODO>]

사용자가 고정한 Source 주소를 기준으로 작성했다. API Key, DB credential, Discord Webhook은 기록하지 않는다.

## 1. Source 목록

| Source ID | 대상 | Endpoint/Base | 방식 | Schedule | Batch/Quota | 증분 기준 | 상태 | Fallback |
|---|---|---|---|---|---|---|---|---|
| SRC-FAQ-001 | FAQ | `http://192.168.0.51:4000/faqs` | HTML 크롤링 | 매일 09:00 KST | `article.faq-item`, 페이지당 4 MiB·allowlist | `data-faq-id`, 없으면 안정 Hash | 계약 관찰 완료, live smoke pending | `tests/fixtures/faq.html` |
| SRC-LIST-001 | 중고차 | `http://192.168.0.51:4000/api/v1/*` | API | 1초마다 Worker | `limit<=500`, 초기 10,000건=최대 20회 | cursor `until_id`/`dataset_epoch`, 증분 `after_seq` | 계약 관찰 완료, live smoke pending | `tests/fixtures/usedcar_*.json` |
| SRC-REG-001 | 자동차등록현황보고 | `https://stat.molit.go.kr/portal/openapi/service/rest/getList.do` | API | 매일 1회 | 실행당 1회, 일일 3,000회 초과 방지 | `start_dt=end_dt=YYYYMM`; 응답 `date`/`월` 보존 | endpoint·form·example response 관찰 완료, key/route pending | `tests/fixtures/registration.json` |

중고차 API 계약은 앞서 확인한 Source 문서의 `/api/v1/public-key`, `/api/v1/cars/cursor`, `/api/v1/changes` 경계를 사용한다. 자동차등록현황보고는 [참고 수집기](../ref/molit_car_registration_daily.py)의 `form_id=5498`, `style_num=2`, `start_dt`/`end_dt` 계약을 사용한다. 현재 실시간 접근이 불가능하므로 live response와 실제 credential은 아직 검증하지 않는다.

## 2. 수집 정책

### FAQ

- `/faqs`와 Source가 제공하는 동일 host의 allow-listed path만 요청한다.
- FAQ 카드의 `data-faq-id`, `data-brand`, `data-category`, `data-reviewed-at`, `data-source-url`과 `data-field` 질문·답변을 사용한다.
- 질문·답변·분류·출처를 수집하고 MongoDB Document로 전처리한다.
- 제공되는 license·attribution·content hash를 보존한다. 필수 정책 metadata가 없으면 write하지 않는다.
- Source 차단·Schema 불일치 시 정상 Document를 삭제하거나 빈 결과를 적재하지 않는다.

### 중고차

- 장기 실행 Python Worker가 1초에 한 번씩 순차 호출한다.
- 1회 최대 500건을 처리한다.
- 초기 1만건이면 500건씩 20회, 호출 간격 1초로 처리한다.
- 초기 동기화 후에는 마지막 성공 Checkpoint 이후만 요청한다.
- Source가 증분 기준값을 제공하지 않으면 incremental_contract_missing으로 중단한다.
- 목록 객체의 `brand`, `model`, `location`, `dealer`, `businessArea`는 반복 참조 엔터티로 취급한다. 안정 ID(`brand.id`, `model.id`, `location.id`, `dealer.code`, `businessArea.id`)와 중첩 필드를 전처리 계약으로 전달한다.
- 수집기는 참조 테이블이나 SQL 컬럼을 알지 않는다. 응답 envelope와 매물 객체 계약만 유지하며, 관계형 분리·FK 순서·Upsert는 적재 단계가 담당한다.

### 자동차등록현황보고

- `https://stat.molit.go.kr/portal/openapi/service/rest/getList.do`에 `form_id=5498`, `style_num=2`, `start_dt`, `end_dt`를 사용한다.
- 매일 한 번 현재 또는 지정된 `YYYYMM`을 `start_dt`와 `end_dt`에 함께 넣어 호출한다.
- API 응답은 `result_data.formList`를 수집 대상으로 사용한다. 각 행의 `date`, `시도명`, `시군구`와 `승용>관용` 같은 모든 지표 키를 보존한다.
- API 호출·재시도는 일일 3,000회 quota에 포함하며, 한 Pipeline 실행은 논리적 호출 1회를 넘기지 않는다.
- 자동으로 과거 월을 역순 탐색하거나 남은 quota를 모두 소진하는 Backfill은 MVP 수집 정책이 아니다.

## 3. 공통 Source Guard

| 확인 항목 | 실패 처리 |
|---|---|
| AWS Backend에서 Source route | 수집 시작 전 blocked |
| robots/license/allowlist | 우회하지 않고 blocked |
| HTTP 403/429 또는 인증 실패 | write 없이 FAILED |
| Schema/selector/field 불일치 | write 없이 FAILED |
| 증분 기준값 미지원 | 중고차 Pipeline incremental_contract_missing |
| 500건·1초 Rate Limit 미확인 | Source 계약 확인 전 운영 실행 금지 |

## 4. Fixture 원칙

- Live Source가 준비되지 않아도 official-shape/versioned fixture로 Must 요구사항을 검증한다.
- Fixture 결과를 운영 DB의 실제 데이터로 가장하지 않는다.
- fixture 버전, checksum, 실행 run_id를 Evidence에 남긴다.

## 5. 미결 Source 질문

| ID | 질문 | owner | 상태 |
|---|---|---|---|
| SRC-OQ-001 | FAQ live response·allowlist·license policy를 운영 환경에서 재확인할 수 있는가? | <TODO> | pending-live |
| SRC-OQ-002 | 중고차 API key·403/429·500건·1초 정책을 운영 환경에서 재확인할 수 있는가? | <TODO> | pending-live |
| SRC-OQ-003 | 중고차 `dataset_epoch`와 `after_seq`가 실제 live response에서도 유지되는가? | <TODO> | pending-live |
| SRC-OQ-004 | 자동차등록현황보고 API key·quota reset 시각·최신 기준일을 운영 계정으로 확인했는가? | <TODO> | pending-live |
| SRC-OQ-005 | AWS에서 192.168.0.51:4000으로 통신할 경로가 있는가? | <TODO> | open |
