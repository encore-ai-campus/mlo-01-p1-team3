# Collection 구현 모듈 이슈 보고서

- 작성일: 2026-08-12
- 대상 저장소: `/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3`
- 대상 모듈: `src/collection`
- 참고 폴더: `/Users/ahh/project/mlo-01-p1-team3-a`
- 목적: 현재 계약에서 동작을 위해 반드시 확정해야 할 구현 이슈와 조건부 계약 이슈를 우선순위별로 보고
- 조치 범위: 분석 및 보고만 수행. 본 보고서 작성 중 소스·테스트·설정 파일은 수정하지 않음

## 1. 판정 기준

| 우선순위 | 의미 |
|---|---|
| P0 | 외부 계약 또는 실행 환경이 확정되지 않아 정상 실행을 승인할 수 없는 차단 이슈 |
| P1 | 런타임 차단은 아니지만 검수 완료와 재현 가능한 실행을 위해 반드시 해소해야 하는 이슈 |
| P1-조건부 | 실제 upstream 응답 또는 상위 호출자의 계약을 확인한 뒤 승격 여부를 결정할 이슈 |

## 2. 요약

| ID | 우선순위 | 모듈 | 이슈 | 현재 판정 |
|---|---|---|---|---|
| COL-001 | P0 | `usedcar.py` | 초기 중고차 API endpoint·pagination 계약 충돌 | 계약 확정 전 승인 불가 |
| COL-002 | P0 | `api.py`, `faq.py`, 의존성 파일 | clean checkout 실행 의존성 및 Git 반영 불완전 | 새 환경 실행 보장 불가 |
| COL-003 | P1 | collection 테스트 | 현재 저장소 기준 단위 테스트 증거 부재 | 완료 기준 미충족 |
| COL-004 | P1-조건부 | `registration.py`, `api.py`, `faq.py` | 오류·무데이터·URL 보호·응답 제한 계약의 조건부 정합성 | 실제 계약 확인 후 승격 |

---

## COL-001. 중고차 초기 수집 API 계약 충돌

### 우선순위

**P0 — 계약 확정 전 동작 승인 불가**

### 관련 구현

현재 저장소 구현은 cursor 방식이다.

- [src/collection/usedcar.py:22](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/collection/usedcar.py:22): `INITIAL_ENDPOINT = "/api/v1/cars/cursor"`
- [src/collection/usedcar.py:232-238](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/collection/usedcar.py:232): `after_id=0`, `limit` 방식의 초기 요청
- [src/collection/README.md:46-49](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/collection/README.md:46): cursor endpoint와 cursor envelope 계약

그러나 참고 폴더의 최신 작업 트리 코드·문서·live evidence는 page 방식이다.

- [reference usedcar.py:20-24](/Users/ahh/project/mlo-01-p1-team3-a/src/collection/usedcar.py:20): `/api/v1/cars`, `sort=newest`, `page_size=100`
- [reference collection README:46-49](/Users/ahh/project/mlo-01-p1-team3-a/src/collection/README.md:46): API 100건 페이지를 논리적 500건으로 aggregation
- [reference source registry:18-21](/Users/ahh/project/mlo-01-p1-team3-a/docs/07_source-registry.md:18): 초기 `page_size<=100`, 논리 Batch `<=500`
- [reference implementation guide:345-347](/Users/ahh/project/mlo-01-p1-team3-a/docs/00_implementation.md:345): `GET /api/v1/cars?sort=newest&page_size=100` 계약

### 확인 결과

현재 소스를 참고 폴더의 page 방식 테스트에 연결하여 실행한 결과:

```text
2 failed, 1 passed, 15 deselected
```

주요 실패는 다음과 같다.

1. page 방식 `links.next`를 현재 cursor endpoint 검증기가 거부함
2. aggregation 테스트가 사용하는 `interval_seconds=0.001`을 현재 구현이 거부함

두 번째 항목은 운영 정책인 1초 간격 자체가 잘못되었다는 뜻은 아니다. 운영에서는 1초 정책을 유지하되, 단위 테스트가 가상 시계로 정책을 검증할 수 있는지 별도 확정해야 한다.

### 핵심 문제

참고 폴더는 최신 코드·문서가 page 방식으로 바뀌었지만 fixture에는 cursor next URL이 남아 있다. 또한 참고 폴더 자체도 해당 변경이 모두 commit된 안정적인 기준선이 아니다. 따라서 현재 상태에서 page 방식으로 임의 변경하거나 cursor 방식으로 임의 승인하면 안 되고, 실제 upstream 계약을 먼저 확정해야 한다.

### 영향

- 실제 API가 page 방식이면 현재 구현의 초기 endpoint와 `links.next` 검증이 실패한다.
- 초기 API 100건 페이지를 논리적 500건으로 묶는 계약이 현재 구현에 없다.
- 실제 API가 cursor 방식이면 참고 폴더의 최신 코드·문서·live evidence와 현재 저장소가 충돌한다.
- 초기 수집 성공 여부, batch 크기, checkpoint 및 후속 pipeline 입력을 판정할 수 없다.

### 확정 요청 및 승인 기준

다음 항목을 담당자가 실제 upstream 응답 또는 공식 계약으로 확인해야 한다.

1. 초기 endpoint: `/api/v1/cars` 또는 `/api/v1/cars/cursor`
2. 초기 요청 파라미터: `sort`, `page_size` 또는 `after_id`, `limit`
3. API 페이지와 논리적 500건 batch의 관계
4. `links.next`, `meta.page`, `meta.total_pages`, `meta.has_more`의 종료 규칙
5. 증분 endpoint의 `after_seq` 및 `limit<=500` 규칙
6. 1초 호출 간격을 운영 및 단위 테스트에서 검증하는 방식

승인하려면 선택한 계약이 `usedcar.py`, `src/collection/README.md`, fixture, 단위 테스트에 동일하게 반영되고, 실제 또는 계약 fixture 기준으로 다음이 확인되어야 한다.

- 첫 요청 URL과 query가 정확함
- 초기 논리 batch가 최대 500건으로 구성됨
- 마지막 페이지에서 next link를 잘못 따라가지 않음
- 증분 checkpoint가 다음 호출에 전달됨
- 요청이 겹치지 않고 시작 시각 기준 1초 간격을 지킴

### 수정 요청 범위

계약 확정 후 다음 범위만 요청한다.

- `src/collection/usedcar.py`
- `src/collection/README.md`
- collection fixture 및 단위 테스트

`preprocessing`, `loading`, DB 적재 모듈은 이 이슈의 직접 수정 범위에서 제외한다.

---

## COL-002. clean checkout 실행 의존성 및 Git 반영 불완전

### 우선순위

**P0 — 새 환경에서 실행 가능하다고 승인할 수 없음**

### 확인된 내용

collection 구현은 다음 외부 패키지를 직접 import한다.

- [src/collection/api.py:17](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/collection/api.py:17): `requests`
- [src/collection/faq.py:14](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/collection/faq.py:14): `bs4`

현재 작업 트리의 [requirements.txt](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/requirements.txt)는 untracked 상태이며, 내용에도 `requests`와 `beautifulsoup4`가 없다. 현재 HEAD에도 `requirements.txt`가 추적되어 있지 않다.

현재 로컬 Conda 환경에서는 import가 성공했지만, 이는 해당 환경에 패키지가 이미 설치되어 있다는 뜻일 뿐 clean checkout 실행을 증명하지 않는다.

### 영향

- GitHub에서 새로 checkout한 환경에 의존성 파일이 없을 수 있다.
- 의존성 설치 후 `collection.api`, `collection.faq` import가 실패할 수 있다.
- 단위 테스트가 로컬 환경 의존성 때문에 통과하는 것처럼 보일 수 있다.

### 확정 요청 및 승인 기준

1. 의존성 파일을 Git 추적 대상으로 확정한다.
2. `requests`, `beautifulsoup4`를 collection 실행 의존성으로 명시한다.
3. clean checkout에서 명시된 의존성만 설치한다.
4. 다음 import와 collection 단위 테스트를 clean 환경에서 실행한다.

```text
collection.api
collection.cars
collection.faq
collection.registration
collection.usedcar
```

이 보고서 범위에서는 `sql-archemy` 표기 오류처럼 SQL/DB 전용 의존성 문제는 별도 이슈로 분리하고 collection 승인 판정에 포함하지 않는다.

### 수정 요청 범위

- 추적할 의존성 파일
- collection import에 필요한 dependency 선언
- clean checkout 검증 절차 또는 CI 테스트

collection 소스의 transport library를 `requests` 또는 표준 library 중 무엇으로 통일할지는 별도 설계 결정이며, 이 이슈의 필수 조건은 실제 구현과 선언된 의존성이 일치하는 것이다.

---

## COL-003. 현재 저장소 기준 collection 단위 테스트 증거 부재

### 우선순위

**P1 — 런타임 차단은 아니지만 검수 완료 기준 미충족**

### 확인된 내용

현재 저장소에서 `git ls-files`로 확인되는 collection 파일은 소스와 README이며, 현재 저장소 기준 `tests/`는 추적되어 있지 않다. 실행에 사용한 테스트는 참고 폴더의 작업 트리 테스트였다.

참고 폴더의 테스트도 안정적인 commit 기준이 아니다.

- 참고 폴더는 `src/collection/usedcar.py`, fixture, 테스트가 모두 수정된 상태다.
- 참고 fixture에는 cursor URL이 남아 있지만 최신 문서·코드는 page URL을 기대한다.
- 따라서 참고 테스트의 통과만으로 현재 저장소의 계약 이행을 증명할 수 없다.

### 실행 증거

현재 소스를 우선 import하여 참고 폴더의 중고차 page 계약 관련 테스트를 실행했다.

```text
2 failed, 1 passed, 15 deselected
```

실패 내용은 COL-001의 endpoint 불일치와 테스트용 interval 설정 불일치였다. 반대로 cursor fixture를 사용하는 기존 테스트 묶음은 통과했으므로, 이 결과는 계약이 확정되었다는 증거가 아니라 fixture가 서로 다른 계약을 가리고 있다는 증거로 판단한다.

### 확정 요청 및 승인 기준

- 현재 저장소 안에 collection 테스트와 fixture가 추적되어야 한다.
- FAQ, registration, usedcar, 공통 API의 정상·실패·allowlist·retry 경계를 각각 검증해야 한다.
- 확정된 usedcar endpoint와 pagination 계약을 실제 테스트가 호출해야 한다.
- 1초 순차 호출은 실제 sleep을 기다리지 않는 가상 시계 방식으로 검증하되, 운영 기본값은 1초인지 확인해야 한다.
- clean checkout에서 전체 collection 단위 테스트 결과가 온전히 출력되고 통과해야 한다.

### 수정 요청 범위

- 현재 저장소의 collection 테스트 디렉터리
- collection fixture
- 테스트 실행 문서 또는 CI command

참고 폴더의 테스트를 그대로 복사하는 것이 목적이 아니라, 현재 저장소의 확정 계약을 검증하는 독립적인 테스트 증거를 확보하는 것이 목적이다.

---

## COL-004. 외부 계약의 오류·무데이터·보호 경계 조건 미확정

### 우선순위

**P1-조건부 — 실제 upstream 응답과 상위 호출자 계약 확인 후 승격**

정상 fixture 경로에서는 FAQ와 registration의 주요 수집 흐름이 동작했으므로 P0으로 올리지 않았다. 다만 아래 조건은 운영 중 false success, 예외 누락, 외부 URL 접근 또는 비정상 응답에 영향을 줄 수 있다.

### 4.1 registration `INFO-200` 무데이터 응답

현재 [registration.py:99-119](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/collection/registration.py:99)는 `status_code`가 `INFO-200`이면 `result_data.formList` 존재 여부를 확인하기 전에 빈 목록을 반환한다.

반면 README의 외부 계약은 `result_data.formList`를 원천 행으로 전달한다고 적고 있다.

- [current collection README:62-68](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/collection/README.md:62)
- [reference collection README:60-68](/Users/ahh/project/mlo-01-p1-team3-a/src/collection/README.md:60)

참고 구현도 HTTP 500의 `INFO-200`을 별도 빈 응답으로 취급하지만, fixture·live 응답에서 최종 빈 데이터 envelope가 `data: []`인지 `result_data.formList: []`인지가 일관되게 확정되어 있지 않다.

확인 요청:

- 실제 `INFO-200` 응답 body를 확보한다.
- 정상 무데이터와 schema 변경을 구분한다.
- 무데이터를 빈 성공으로 인정할지, `result_data.formList=[]`만 인정할지 결정한다.

### 4.2 registration 네트워크 오류 타입

현재 최종 `URLError` 또는 `TimeoutError`는 [registration.py:225-230](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/collection/registration.py:225)에서 `ApiError`로 변환된다. 그러나 모듈 계약과 참고 구현은 registration upstream 오류를 `RegistrationError`로 처리하는 형태다.

확인 요청:

- 상위 pipeline이 `RegistrationError`를 구체적으로 catch하는지 확인한다.
- registration의 모든 upstream·schema 오류를 `RegistrationError`로 통일할지 결정한다.
- 현재처럼 `ApiError`를 허용한다면 그 계약을 README와 테스트에 명시한다.

### 4.3 registration endpoint scheme 검증

현재 [registration.py:151-160](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/collection/registration.py:151)는 `netloc`만 확인하고 `http` 또는 `https` scheme을 별도로 제한하지 않는다. 따라서 host만 같은 비HTTP URL이 설정 단계에서 거부되지 않을 수 있다.

확인 요청:

- 외부 계약상 `https://stat.molit.go.kr/...`만 허용할지 확정한다.
- 허용 scheme을 `http`까지 포함할 경우 그 이유와 운영 환경을 문서화한다.

### 4.4 AutoData 응답 크기 보호

현재 [api.py:239-265](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/collection/api.py:239)는 `requests.Response.json()`을 직접 호출한다. FAQ는 4 MiB, registration은 8 MiB 제한을 구현하고 있지만, AutoData 공통 API의 일반 응답 body에는 동일한 상한 검사가 보이지 않는다.

참고 폴더의 API 구현과 문서는 AutoData 응답 8 MiB 제한을 기준으로 한다. 이 제한이 실제 운영 계약인지 단순한 방어 정책인지 확인해야 한다.

확인 요청:

- AutoData 응답 최대 크기를 계약으로 둘지 결정한다.
- 계약이면 초과 응답을 JSON parse 전에 `response_too_large`로 중단하고 테스트한다.

### 4.5 FAQ 페이지 수 제한

현재 [faq.py:199-217](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/collection/faq.py:199)는 기본 `FAQ_MAX_PAGES=100`을 사용하고, next link가 남은 상태로 100페이지에 도달하면 오류를 낸다. 참고 폴더의 구현 가이드도 `FAQ_MAX_PAGES=100`을 사용하므로 현재 자료 사이에 직접적인 불일치는 확인되지 않았다.

따라서 FAQ 페이지 수는 현재 P1 이슈로 확정하지 않는다. 상위 요구사항에서 별도의 최대 페이지 수를 요구한다면 그 값을 확정한 뒤 이 항목을 승격한다.

### 조건부 승인 기준

다음 중 하나라도 운영 계약으로 확인되면 해당 sub-issue를 P1로 승격한다.

- `INFO-200` 응답 envelope가 현재 parser와 다름
- 상위 호출자가 `RegistrationError`를 요구함
- registration은 HTTPS만 허용해야 함
- AutoData 응답 크기 상한이 필수임
- FAQ 최대 페이지 수가 현재 기본값 100과 다름

승격된 항목은 실제 응답 fixture, 오류 타입, 문서, 단위 테스트를 함께 수정·검증해야 한다. 실제 계약이 현재 구현과 일치한다면 “문제 없음”으로 종결하고 별도 수정 요청을 만들지 않는다.

---

## 3. 범위 외 발견 사항

참고 폴더 전체 테스트를 실행할 때 `common/config` 및 logging 관련 실패가 추가로 관찰되었으나, 요청 범위인 `src/collection` 외 파일의 문제이므로 본 보고서의 수정 범위와 우선순위에는 포함하지 않는다.

## 4. 최종 요청 순서

1. COL-001: 실제 중고차 초기 API 계약 확정
2. COL-002: clean checkout 의존성 및 Git 반영 확정
3. COL-003: 현재 저장소 기준 collection 단위 테스트 확보
4. COL-004: 실제 registration·AutoData·FAQ 응답과 상위 호출자 계약 확인 후 조건부 승격 판단

COL-001~COL-003이 닫히고, COL-004의 조건부 항목이 계약상 문제없음 또는 검증 완료로 판정되어야 collection 모듈의 동작 검수를 완료할 수 있다.


## 5. 결정사항
1. COL-001: cursor 방식을 사용한다.
  - 참고폴더의 문서는 구현 또는 검증에 참고자료일 뿐 SSOT로 인지하여서는 아니된다.
  - 근거: [http://43.203.233.157/docs](http://43.203.233.157/docs) API ENDPOINTS 경로 내역 중 '대량 적재용 ID 커서 목록' 구문 확인
2. COL-002: requirements.txt에 해당 의존성을 추가한다.
  - 지시자가 수정 이후 수동 커밋하여 해당 파일을 추적한다.
  - 근거: git status 내역 중 Untracked 영역 확인
3. COL-003: mlo-01-p1-team3/tests/ 에 단위 테스트를 구현한다.
  - 이후 모든 작업은 TDD로 진행되어야 한다.
  - 단위 테스트는 해당 모듈의 정상동작을 검증하는 과정이며, 전체 파이프라인의 정상동작을 보장하지 않는다.
  - 근거: tests폴더 부재 확인 및 colloction폴더의 모든 로직 내부 테스트 요소 미구현 확인
