# Preprocessing 구현 모듈 이슈 보고서

- 작성일: 2026-08-13
- 대상 저장소: `/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3`
- 대상 모듈: `src/preprocessing`
- 참고 폴더: `/Users/ahh/project/mlo-01-p1-team3-a`
- 목적: 현재 계약상 정상 동작을 승인하기 위해 반드시 확인·확정해야 하는 preprocessing 구현 이슈를 우선순위별로 보고
- 보고 상태: 아래 `5. 결정사항`의 지시자 결정과 현재 저장소 검증 결과를 본문에 반영
- 이번 갱신 범위: 이슈 보고서만 수정하며, 결정사항 원문은 변경하지 않음

## 0. 결정 반영 상태

아래 `5. 결정사항`은 지시자가 작성한 원문을 유지한다. 본 절과 각 이슈의 현재 판정만 해당 결정사항에 맞춰 동기화한다.

| ID | 결정 및 현재 상태 |
|---|---|
| PRE-001 | 반영 완료. `ref/mlo-01-p1-team3-a/`는 참고용으로만 취급하고 현재 저장소 `tests/`를 테스트 기준으로 사용한다. 현재 `ref/` 경로가 import 경계에 개입하지 않는지 확인한 결과도 본문에 기록한다. |
| PRE-002 | 반영 완료. `tests/test_preprocessing.py`에 preprocessing 단위 테스트가 존재하며 `32 passed`를 확인했다. 이후 변경은 TDD로 진행하고, 이 결과를 전체 pipeline 통과로 해석하지 않는다. |
| PRE-003 | 반영 완료. FAQ 전처리부의 날짜 전용 형식을 유지하고 collection FAQ fixture를 수정했다. collection-to-preprocessing 호환 테스트가 통과한다. |
| PRE-004 | 반영 완료. README에 시간 의미별 책임과 FAQ canonical field를 명시했고, 구현·loading·테스트와의 정합성을 확인했다. |
| PRE-005 | 반영 완료. 참고 폴더의 구현·테스트 결과는 통과 근거로 사용하지 않고, 현재 저장소 `tests/`에서 확인되는 테스트 결과를 증거로 사용한다. GitHub 반영 여부는 별도 Git 상태로 확인한다. |

## 1. 판정 기준

| 우선순위 | 의미 |
|---|---|
| P0 | 테스트 실행 또는 대상 모듈의 검증 증거가 확보되지 않아 정상 실행을 승인할 수 없는 차단 이슈 |
| P1 | 정상 fixture 경로는 실행될 수 있으나 외부 계약 정합성 또는 재현 가능한 검수를 위해 반드시 확정해야 하는 이슈 |

## 2. 요약

현재 대상 저장소와 참고 폴더의 `src/preprocessing` 파일은 byte-level로 동일하다. 다만 PRE-001·PRE-005 결정에 따라 이 동일성이나 참고 폴더의 테스트 결과를 대상 구현의 통과 근거로 사용하지 않는다. 현재 저장소의 `tests/`에서 확인되는 테스트 결과를 기준으로 판정하고, GitHub 반영 여부는 별도로 확인한다.

현재 대상 저장소에는 preprocessing 전용 테스트가 추가되어 있으며 `python -m pytest -q tests/test_preprocessing.py` 결과는 `32 passed`이다. FAQ collection fixture는 날짜 전용 `YYYY-MM-DD` 입력으로 정리되었고 collection-to-preprocessing 회귀 테스트도 통과한다. 이 결과는 preprocessing 모듈 단위 정상동작의 근거이며, 결정사항에 따라 전체 pipeline 정상동작을 보장하지 않는다.

PRE-004의 README·구현·하위 loading 계약 정합성 확인이 완료되었다. FAQ 입력 `reviewed_at`과 준비 출력 `source_updated_at`을 분리하고, `created_at`·`updated_at`은 loading 소유의 적재 시각으로 문서화했다.

| ID | 우선순위 | 모듈 | 이슈 | 현재 판정 |
|---|---|---|---|---|
| PRE-001 | P0 | 테스트 실행 경계 | `ref/`를 검증 기준에서 제외하고 현재 저장소 `tests/`만 탐색하도록 확정 | 반영 완료. `pytest.ini` 기준 `72 tests collected`, `ref/` import 경로 개입 없음 확인 |
| PRE-002 | P0 | preprocessing 테스트 | 대상 저장소에 preprocessing 전용 단위 테스트가 없어 내부·외부 계약을 검증할 수 없었던 문제 | 반영 완료. `tests/test_preprocessing.py` `32 passed`; TDD 지속 |
| PRE-003 | P1 | `faq.py`·FAQ fixture | collection fixture의 ISO datetime과 전처리부의 날짜 전용 입력 계약 불일치 | 반영 완료. 날짜 전용 형식 유지 및 호환 테스트 통과 |
| PRE-004 | P1 | `faq.py`, README | README와 구현·하위 계약의 필드명·날짜 형식 정합성 확인 | 반영 완료. README·구현·loading·테스트 일치 확인 |
| PRE-005 | P1 | 참고 기준·Git 증거 | 참고 폴더의 테스트 결과를 대상 구현의 통과 근거로 사용할 수 없음 | 반영 완료. 현재 저장소 `tests/`의 결과를 증거로 사용하고 GitHub 반영 여부는 별도 확인 |

---

## PRE-001. 대상 전체 테스트 실행 경계와 내부 참고 폴더 충돌 (해소)

### 우선순위

**P0 — 테스트 경계 확정으로 해소**

### 관련 구현 및 테스트 경계

대상 저장소 내부에는 외부 참고 폴더와 별개로 `ref/mlo-01-p1-team3-a/` 복사본이 존재한다. 해당 복사본의 테스트 설정은 자신의 `src` 경로를 pytest import 경로에 삽입한다.

- [대상 내부 참고 테스트 설정](</Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/ref/mlo-01-p1-team3-a/tests/conftest.py:7>)
- [대상 preprocessing 패키지](</Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/preprocessing>)

### 확인 결과

현재 대상 저장소의 테스트 경계는 다음과 같이 고정되어 있다.

```text
pytest.ini: testpaths = tests
tests/conftest.py: 대상 저장소의 src만 sys.path에 추가
```

따라서 `ref/mlo-01-p1-team3-a/` 내부 테스트의 `conftest.py`는 기본 테스트 탐색 대상이 아니다. 현재 설정과 테스트 파일을 확인한 범위에서 `ref/` 경로를 대상 테스트의 import 경로에 삽입하는 코드는 확인되지 않았다.

현재 대상 저장소에서 다음 결과를 확인했다.

```text
python -m pytest --collect-only -q
72 tests collected

python -m pytest -q
72 passed
```

위 결과는 현재 저장소 `tests/`만 대상으로 하며, `ref/` 내부 테스트의 통과 여부를 포함하지 않는다.

### 영향

- 참고 폴더의 테스트 결과가 대상 저장소의 검증 결과에 섞이지 않는다.
- 현재 대상 저장소의 테스트 수집·실행 결과를 파일 경로 기준으로 재현할 수 있다.
- 이후 `ref/` 경로가 import 경계에 개입하면 별도 확인·보고해야 한다.

### 확정 요청 및 승인 기준

1. 대상 저장소의 테스트 탐색 범위와 참고 폴더의 역할을 현재 결정사항대로 유지한다.
2. 대상 테스트 실행 시 `ref/`의 `conftest.py` 또는 테스트가 import 경로에 개입하지 않는지 변경 시마다 확인한다.
3. 대상 저장소에서 다음 명령을 실행하여 수집 오류 없이 결과를 확인한다.

```text
python -m pytest -q
```

4. 출력된 테스트가 대상 저장소의 preprocessing·관련 fixture를 검증하는지 파일 경로를 확인한다.

현재 위 승인 기준을 충족하여 PRE-001은 차단 이슈에서 해소되었다.

### 수정 요청 범위

이번 결정으로 `ref/`는 순수 참고 범위로 확정되었고, 현재 저장소 `tests/`가 검증 기준이 되었다. `src/preprocessing` 소스의 동작을 참고 폴더 결과만으로 수정하지 않는다.

---

## PRE-002. 대상 저장소의 preprocessing 전용 단위 테스트 및 검증 증거 부재 (해소)

### 우선순위

**P0 — 단위 테스트 구현 및 `32 passed` 확인으로 해소**

### 확인된 내용

대상 저장소의 `tests/`에는 preprocessing 전용 테스트 파일이 존재한다.

- [대상 preprocessing 단위 테스트](</Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/tests/test_preprocessing.py>)
- 대상 저장소의 `tests/test_preprocessing.py`는 현재 저장소 테스트 기준에 포함된다.
- 참고 폴더의 별도 테스트는 구현 통과 근거로 사용하지 않는다.

대상 preprocessing README는 다음 계약을 명시한다.

- FAQ·중고차·등록현황을 각각 준비 계약으로 변환
- 필수값·타입·Business Key·content hash 검증
- 모든 변환기가 `(valid_records, rejected_records)` 반환
- 네트워크·DB·SQL driver·MongoDB driver를 import하지 않음

근거: [preprocessing README](</Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/preprocessing/README.md:3>) 및 [의존성 경계](</Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/preprocessing/README.md:68>)

### 확인 결과

현재 대상 저장소의 preprocessing 전용 단위 테스트 실행 결과는 다음과 같다.

```text
python -m pytest -q tests/test_preprocessing.py
32 passed
```

테스트에는 정상 입력, 필수값·타입·Business Key 오류, FAQ fallback ID와 content hash, 중고차 중첩 참조 객체, 등록현황 행 분해·Reject, 변환기 반환 형식, 외부 계층 import 금지 경계가 포함된다.

현재 결과는 preprocessing 모듈 단위 정상동작의 검증 증거로 사용할 수 있다. 다만 결정사항에 따라 이 결과를 전체 pipeline 정상동작의 보장으로 확대하지 않는다.

### 영향

- 대상 저장소의 preprocessing 계약을 현재 `tests/`에서 재현할 수 있다.
- 참고 폴더의 테스트 결과가 대상 구현의 통과 근거로 혼입되지 않는다.
- 이후 변경은 TDD로 진행하여 단위 테스트가 계약 회귀를 검출하도록 한다.

### 확정 요청 및 승인 기준

1. `tests/`에 preprocessing 모듈 단위 테스트를 유지한다.
2. FAQ, 중고차, 등록현황 각각의 정상·거부·경계 입력을 변경 전 테스트로 고정한다.
3. 출력 필드와 `(valid_records, rejected_records)` 반환 계약을 테스트로 유지한다.
4. import 경계 테스트를 대상 저장소에서 독립 실행한다.
5. 이 결과는 preprocessing 모듈 단위 검증으로만 보고하고 전체 pipeline 검증과 구분한다.

### 수정 요청 범위

- `tests/test_preprocessing.py` 단위 테스트 유지
- preprocessing 테스트 fixture 유지
- `pytest.ini`와 `tests/conftest.py`의 테스트 실행 경계 유지

PRE-002의 단위 테스트 구현 및 현재 결과 확인은 완료되었다. 이후 preprocessing 변경은 TDD로 진행한다.

---

## PRE-003. FAQ 날짜 입력 형식과 전처리 허용 형식 불일치 (해소)

### 우선순위

**P1 — 날짜 전용 계약 확정 및 fixture 정합성 반영으로 해소**

### 관련 구현

현재 FAQ 전처리부는 `reviewed_at`을 다음 두 형식만 허용한다.

- `YYYY-MM-DD`
- `YYYYMMDD`

그 외 값은 `invalid_reviewed_at`으로 Reject한다.

- [`_iso_date`](</Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/preprocessing/faq.py:51>)
- [`reviewed_at` 필수값 처리](</Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/preprocessing/faq.py:88>)

현재 대상 collection FAQ fixture는 전처리부가 허용하는 날짜 전용 값을 생성한다.

- [FAQ collection fixture](</Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/tests/test_collection_faq.py:20>)
- 입력 예시: `2026-08-01`

### 확인 결과

현재 collection fixture를 preprocessing에 연결하면 날짜 전용 입력이 정상 변환된다. ISO datetime 입력은 현재 FAQ 전처리 계약의 허용 범위 밖이므로 `invalid_reviewed_at`으로 Reject되는 동작을 유지한다.

```text
input:    2026-08-01
valid:    1
rejected: 0
output:   source_updated_at=2026-08-01T00:00:00+00:00
```

`tests/test_collection_faq.py::test_collection_faq_date_contract_is_accepted_by_preprocessing`에서 이 연결 계약을 회귀 테스트로 고정했으며, 현재 collection FAQ 테스트와 preprocessing 테스트가 통과한다. 이는 PRE-003 결정에 따라 FAQ 전처리부의 날짜 전용 형식을 유지하고 collection fixture를 그 형식에 맞춘 결과다.

### 영향

- 현재 collection fixture와 FAQ preprocessing의 날짜 입력 형식은 일치한다.
- 실제 upstream 형식이 변경되면 collection fixture와 preprocessing 계약의 재검증이 필요하다.
- `reviewed_at` 입력은 날짜 전용으로 유지하고, 전처리 출력의 canonical field는 `source_updated_at`으로 고정한다.

### 확정 요청 및 승인 기준

PRE-003 결정에 따라 현재 FAQ 원천 입력 계약은 날짜 전용 형식으로 확정하고 전처리부의 허용 형식을 유지한다. 다음 항목은 같은 형식을 사용해야 한다.

- collection parser 출력
- preprocessing 입력 검증
- preprocessing 단위 테스트 fixture
- README와 외부 데이터 계약 문서

현재 날짜 전용 정상 형식은 valid로 변환되고, ISO datetime 및 달력상 무효 값은 의도한 `Reject` code로 검증된다.

### 수정 요청 범위

결정사항에 따른 현재 반영 범위는 다음과 같다.

- FAQ collection parser 또는 fixture
- `src/preprocessing/faq.py`의 날짜 전용 허용 형식 유지
- collection FAQ fixture의 날짜 전용 값
- preprocessing 및 FAQ 관련 단위 테스트
- 관련 README·데이터 계약 문서의 형식 설명

현재 PRE-003은 collection fixture 수정과 호환 테스트 통과로 해소되었다. 실제 원천 응답 변경이 확인될 때만 별도 계약 재검토가 필요하다.

---

## PRE-004. FAQ 출력 필드명 `reviewed_at`과 `source_updated_at` 불일치 (해소)

### 우선순위

**P1 — canonical field 확정 및 README·구현·하위 계약 정합성 확인으로 해소**

### 확인된 내용

현재 preprocessing README는 FAQ의 외부 입력 field와 내부 출력 field를 분리하여 명시한다.

- 외부 입력: `reviewed_at` — `YYYY-MM-DD` 또는 `YYYYMMDD` 날짜 전용
- 내부 출력: `source_updated_at` — UTC 자정 기준 `YYYY-MM-DDT00:00:00+00:00`
- [FAQ 계약 및 시간 책임](</Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/preprocessing/README.md:107>)

현재 구현도 입력 `reviewed_at`을 정규화한 뒤 출력 mapping에 `source_updated_at`으로 반환한다.

- [FAQ 입력 정규화](</Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/preprocessing/faq.py:88>)
- [FAQ 출력 mapping](</Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/preprocessing/faq.py:122>)

loading 및 테스트도 동일한 field 구분을 사용한다. FAQ loading은 준비 document의 field를 그대로 저장하고, 중고차·등록현황 loading의 source timestamp field도 `source_updated_at`으로 통일되어 있다. 참고 폴더의 구현·테스트 결과는 이 판정의 근거로 사용하지 않았다.

### 영향

- 외부 입력과 내부 출력 field가 분리되어 계약 혼동이 발생하지 않는다.
- content hash는 `source_updated_at`을 안정 field로 사용하고, 실행 metadata와 분리된다.
- README의 시간 책임 표와 sequence diagram이 실제 preprocessing·loading 경계를 설명한다.

### 확정 요청 및 승인 기준

FAQ 준비 계약의 canonical field는 `source_updated_at`으로 확정한다. 외부 입력 field `reviewed_at`은 입력 전용으로 유지한다. 다음 위치의 정합성을 확인했다.

- `src/preprocessing/README.md`
- `transform_faq_record()` 반환 mapping
- FAQ 단위 테스트와 fixture
- loading·pipeline handoff 호출부
- 데이터 명세 및 필드 매핑 문서

동일 의미의 `reviewed_at` 별칭을 준비 출력에 중복 생성하지 않으며, 날짜 형식은 FAQ collection fixture·preprocessing·테스트에서 날짜 전용으로 고정한다. `created_at`·`updated_at`의 생성 책임은 loading으로 분리한다.

현재 저장소 루트에 `migrations/`가 없어 실제 DB schema column mapping까지는 검증하지 못했다. 이 부분은 본 보고서의 범위 외 발견 사항으로 남기며, preprocessing·loading·pipeline handoff의 field 정합성 판정과 분리한다.

### 수정 요청 범위

README에 내부 계약, 외부 계약, 시간 책임, 예시와 sequence 설명을 반영했고, FAQ preprocessing·loading·테스트의 field 정합성을 확인했다. pipeline 실행·checkpoint formatter call site는 preprocessing 외부의 pipeline 모듈 책임으로 남긴다.

현재 PRE-004는 해소되었다. 이후 field명 또는 시간 의미를 변경할 때는 `tests/`에 실패 테스트를 먼저 추가하고 README·하위 계약을 함께 갱신한다.

---

## PRE-005. 참고 폴더 테스트 결과의 commit 재현성 부재 (해소)

### 우선순위

**P1 — 참고 결과를 대상 구현의 확정 증거로 사용할 수 없음**

### 확인된 내용

참고 폴더 `/Users/ahh/project/mlo-01-p1-team3-a`는 과거 구현 참고용 폴더로만 취급한다. 참고 폴더의 working tree 또는 테스트 결과는 대상 저장소 구현의 통과 근거로 사용하지 않는다.

현재 대상 저장소에서 검증 근거로 사용하는 결과는 다음과 같다.

```text
python -m pytest -q tests/test_preprocessing.py
32 passed

python -m pytest -q
72 passed
```

위 결과는 현재 저장소의 `tests/`와 현재 작업 기준에서 실행한 결과다. 참고 폴더의 구현·테스트와 독립적으로 대상 저장소의 preprocessing 테스트 증거가 존재한다. 단, 현재 작업 트리의 untracked 파일 전체가 commit되었다는 의미는 아니며, GitHub 반영 여부는 별도 Git 작업으로 확인해야 한다.

### 영향

- 참고 폴더 결과를 대상 구현의 통과 근거로 오인하지 않게 되었다.
- 현재 저장소의 preprocessing 단위 테스트와 전체 테스트 결과를 독립적으로 재현할 수 있다.
- 테스트 파일의 Git 추적·commit·GitHub 반영 여부는 실제 Git 상태를 기준으로 별도 확인해야 한다.

### 확정 요청 및 승인 기준

1. 참고 폴더는 순수 참고자료로 유지한다.
2. 대상 저장소의 `tests/`를 preprocessing 검증 기준으로 유지한다.
3. 변경된 테스트 파일의 Git 추적·commit·GitHub 반영 여부는 작업 단위마다 확인한다.
4. 대상 저장소에서 preprocessing 단위 테스트와 전체 테스트를 실행한다.
5. 테스트 결과와 대상 commit을 함께 기록한다.

현재 결정된 검증 경계와 대상 저장소 테스트 증거 확보 기준은 충족했다.

### 수정 요청 범위

이 이슈의 직접 범위는 검증 기준과 테스트 증거의 분리·보존이다. 참고 폴더의 미관련 모듈 변경이나 전체 pipeline 수정은 포함하지 않는다.

## 3. 범위 외 발견 사항

대상 저장소 루트에는 `migrations/`가 없어 SQL schema·DB loading 계약을 preprocessing과 연결하여 검증할 수 없다. 이는 preprocessing 파일 외부의 문제이므로 본 보고서에서는 언급만 하고 수정 범위에서 제외한다.

또한 collection·loading·pipeline 구현의 참고 폴더와 대상 저장소 간 차이는 전체 pipeline 조사 대상이지만, 본 보고서의 preprocessing 필수 이슈 우선순위에는 별도 항목으로 산정하지 않는다.

## 4. 현재 후속 조치 순서

1. 변경 전 대상 `tests/`에 실패 테스트를 먼저 추가하고 TDD로 구현
2. 시간 field 또는 책임 변경 시 preprocessing README·하위 loading 계약·테스트를 함께 갱신
3. preprocessing 단위 테스트와 전체 테스트를 구분하여 재실행

현재 PRE-001부터 PRE-005까지 결정사항 반영 및 대상 저장소 테스트 검증으로 해소되었다. preprocessing 전용 테스트 `32 passed`, 전체 테스트 `72 passed`를 확인했으며, 이 결과는 preprocessing 모듈 검증 완료를 의미하고 전체 pipeline 정상동작 보장을 의미하지 않는다.

## 5. 결정사항

1. PRE-001: ref/mlo-01-p1-team3-a/ 폴더는 과거 구현 시 참고용 폴더일 뿐 추가적인 의미를 가지지 않는다. 
    - 테스트는 'mlo-01-p1-team3/tests/' 위치에 존재하는 것으로 확정한다.
    - ref/* 내의 테스트 등이 import 경로에 개입은 추가적으로 확인 후 보고하여야 한다.
    - 근거: tests/ 모듈을 fix/validate-collection 브랜치에서 생성하였고 자체적인 테스트 파일이 존재하지 않았음
2. PRE-002: mlo-01-p1-team3/tests/ 에 단위 테스트를 구현한다.
    - 이후 모든 작업은 TDD로 진행되어야 한다.
    - 단위 테스트는 해당 모듈의 정상동작을 검증하는 과정이며, 전체 파이프라인의 정상동작을 보장하지 않는다.
    - 근거: tests폴더 부재 확인 및 proprocessing폴더의 모든 로직 내부 테스트 요소 미구현 확인
3. PRE-003: FAQ 전처리부의 형식을  유지한다.
    - 코드 및 실행결과 collection FAQ fixture의 외부계약 불일치 확인
    - collection fixture 수정 완료
    - 근거: [http://43.203.233.157/faqs](http://43.203.233.157/faqs) 원본 데이터 형식 확인
4. PRE-004: 현재 구현 모듈 README는 현재 불일치가 존재하여 전수 조사중인 상황에서 신뢰할 수 없다.
    - 종합적으로 판단하여 보다 타당성 높은 결정을 진행하여야 한다. 동일 로직 내 타 모듈의 Date 형식 등을 확인하여 확정한다.
    - README.md 수정 시 명확히 명시하여 이후 동일 문제가 발생하지 않도록 고정하여야 한다.
5. PRE-005: mlo-01-p1-team3/tests/ 에 단위 테스트를 구현한다.
    - 참고 폴더의 구현사항은 순수 참고자료로 활용하여야하며 이 외의 구현 통과 근거로써 사용할 수 없다.
    - 단위 테스트는 해당 모듈의 정상동작을 검증하는 과정이며, 전체 파이프라인의 정상동작을 보장하지 않는다.
    - 근거: tests폴더 부재 확인 및 proprocessing폴더의 모든 로직 내부 테스트 요소 미구현 확인
