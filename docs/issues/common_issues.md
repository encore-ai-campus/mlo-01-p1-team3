# Common 구현 모듈 이슈 보고서

- 작성일: 2026-08-13
- 대상 저장소: `C:\encore_first_project`
- 대상 모듈: `src/common`
- 직접 연관 모듈: `src/loading`
- 참고 저장소: `C:\encore_first_project\ref\mlo-01-p1-team3-a`
- 참고 보고서: `C:\Users\yoona\OneDrive\Desktop\# common 구현 모듈 이슈 보고서.md`
- 목적: 공통 설정·계약·로그·SQL 변환 모듈의 내부 계약, 외부 계약, 문서 정합성, 테스트 증거 및 운영 안전성 보고
- 조치 범위: `common.logging_utils` 경로·공통 테스트·관련 문서만 정리했으며 collection/loading 구현은 수정하지 않음
- MongoDB 상태: `.env`에 URI·인증 변수는 존재하나 실제 연결·인증·선출 검증은 보류

## 0. 결정 반영 및 현재 상태

| ID | 우선순위 | 항목 | 현재 판정 |
|---|---|---|---|
| COM-001 | P2-조건부 | `src/common` 전용 테스트 증거 | 전용 테스트 파일은 존재하며 10개 함수의 직접 검증은 통과했으나 현재 런타임에 pytest가 없어 native pytest 결과는 보류 |
| COM-002 | P2 | `common` 파일·README·export 정합성 | 현재 작업 트리 기준 이상 없음 |
| COM-003 | P1 | production MongoDB URI scheme 검증 부족 | 잘못된 scheme이 설정 단계에서 통과할 수 있음 |
| COM-004 | P1 | 명시적 URI와 별도 MongoDB 인증정보 계약 충돌 | 설정은 통과하지만 loader가 별도 인증정보를 URI에 반영하지 않음 |
| COM-005 | P1-조건부 | 실제 Replica Set URI·DB 연결 검증 | URI·인증 변수는 설정되어 있으나 실제 DB 미연결로 검증 보류 |
| COM-006 | P1-조건부 | `RunContext` reference source와 문서의 signature 차이 | current 코드는 문서와 일치하지만 reference source와 positional 호환성이 다름 |
| COM-007 | P2 | 로그 마스킹의 일반 `key` 과잉 매칭 | 정상 문자열 일부가 `[REDACTED]`로 변형될 수 있음 |
| COM-008 | P2 | README의 host 하드코딩 설명과 fallback 코드 불일치 | 문서 표현과 실제 기본값이 다름 |
| COM-009 | P1-조건부 | 실제 외부 API·MySQL·MongoDB 동작 검증 부재 | fixture·mock 범위 밖의 운영 동작은 승인할 수 없음 |
| COM-010 | P2-조건부 | project root 외부 import 경로 의존 | `common`을 사용하려면 `src`를 Python path에 추가하거나 package로 설치해야 함 |

## 1. 판정 기준

| 우선순위 | 의미 |
|---|---|
| P0 | 계약 또는 보안 문제가 확정되어 동작 승인 불가 |
| P1 | 운영·검수 완료를 막거나 실제 계약 확인 전 승인 불가 |
| P1-조건부 | 실제 외부 계약·상위 호출자·운영환경 확인 시 승격 가능 |
| P2 | 기능 실행은 가능하지만 문서·호환성·관측성·유지보수 위험이 있음 |

## 2. 테스트 및 정합성 확인 결과

### 2.1 현재 저장소에 저장된 테스트 파일

현재 저장소에는 다음 `src/common` 전용 테스트 파일이 있다.

- `C:\encore_first_project\tests\test_common_config.py`
- `C:\encore_first_project\tests\test_common_contracts.py`
- `C:\encore_first_project\tests\test_common_logging_utils.py`
- `C:\encore_first_project\tests\test_common_sql_utils.py`
- `C:\encore_first_project\tests\test_common_time_utils.py`

참고 폴더의 테스트는 별도로 collection·preprocessing·loading·pipeline fixture를 검증하며, 이번 common 범위에는 포함하지 않았다.

### 2.2 실행한 검증

| 검증 | 결과 | 한계 |
|---|---:|---|
| `src/common` 전용 직접 테스트 harness | `10 passed, 0 failed` | 현재 런타임에 pytest가 없어 native pytest 실행 결과는 확인하지 못함 |
| 전체 `src` compile 검사 | 통과 | 문법만 검증하며 외부 시스템 연결은 검증하지 않음 |
| 레퍼런스 테스트 | `16 passed` | fixture·JSON sink 중심이며 실제 운영 DB/API 연결은 포함하지 않음 |
| common README 파일 목록·`__all__` 검사 | 이상 없음 | 정적 구조 검증만 수행 |
| 공통 모듈 reverse-stage import 검사 | 이상 없음 | 동적 import 경로는 제한적으로만 확인 |
| `Settings` 사용 필드 검사 | 미확인 필드 0개 | `getattr()` 등 동적 접근은 정적 검사 한계가 있음 |
| 루트 `.env` 키 정합성 | 44개 키, unknown 0개 | 실제 비밀값의 유효성·권한은 검증하지 않음 |
| MongoDB 전체 URI forwarding | mock `MongoClient`에 원문 URI 전달 확인 | 실제 Replica Set discovery·인증·쓰기 미검증 |

### 2.3 테스트 코드 부재로 검증이 어려운 항목

다음 항목은 현재 저장소에 재현 가능한 전용 테스트가 없어 승인할 수 없다.

1. 실제 `MongoClient`의 Replica Set 전체 host discovery 및 `replicaSet` 옵션 동작
2. MongoDB 인증 실패·Primary election·Secondary read/write 정책
3. MySQL 연결, timezone/session 설정, 실제 transaction·upsert·replication 상태
4. production `APP_ENV`에서 EnvironmentFile 또는 systemd가 주입하는 값의 우선순위
5. 실제 외부 API의 응답 크기·schema 변경·timeout·HTTP 오류 계약
6. clean checkout에서 별도 설치 없이 공통 모듈과 전체 pipeline을 import하는지 여부
7. `common.logging_utils`를 project root 외부에서 호출할 때의 `PYTHONPATH`·package 설치 방식

일회성 검사 결과만으로 위 항목을 통과했다고 판정할 수 없다.

---

## COM-001. `src/common` 전용 테스트 증거

### 우선순위

**P2-조건부 — 테스트 파일은 존재하나 native pytest 실행 환경 확인 필요**

### 확인 내용

`config`, `contracts`, `logging_utils`, `sql_utils`, `time_utils`별 전용 테스트 파일이 저장되어 있다. wrapper를 참조하던 logging 테스트는 제거 후 `common.logging_utils`의 구현 module ownership과 redaction·JSONL 출력을 직접 검증하도록 변경했다. 의존성 없는 직접 harness에서는 10개 테스트 함수가 통과했다.

### 영향

- native pytest가 설치되지 않은 환경에서는 표준 pytest 결과를 재현할 수 없다.
- `Settings` production 검증, secret redaction, SQL 날짜 변환의 경계값을 CI에서 반복 검증할 수 없다.
- 실제 MongoDB·MySQL·외부 API 연결은 이 단위 테스트 범위에 포함되지 않는다.

### 승인 기준

- CI 또는 clean checkout에 pytest를 설치하고 동일한 `tests/test_common_*.py` 명령을 실행한다.
- 실제 DB/API 검증은 별도 통합 테스트 환경에서 수행한다.

이번 정리에서는 common 전용 테스트 파일을 유지하고 구 logging wrapper 의존성을 제거했다.

---

## COM-002. `common` 파일·README·public export 정합성

### 판정

**현재 작업 트리 기준 문제 없음.**

다음 항목은 일치했다.

- README의 파일 목록과 실제 `common/*.py` 5개 파일
- `common`, `common.config`, `common.contracts`, `common.logging_utils`, `common.sql_utils`의 `__all__`
- `common` 모듈에서 `collection`, `preprocessing`, `loading`, `pipelines`로 향하는 역방향 import 부재
- `Settings` 속성 사용처와 dataclass 필드
- 루트 `.env` 44개 key와 `config.py`가 해석하는 환경변수 이름

`common.logging_utils`는 [직접 구현체](C:/encore_first_project/src/common/logging_utils.py)이며, 레퍼런스의 `common/logging_utils.py` 배치와 일치한다. 기존 별도 logging 영역의 호환 wrapper와 README는 제거했고, 내부 import·테스트는 `common.logging_utils`만 사용한다. 외부 배포물이 제거된 이전 경로를 직접 호출한다면 별도 마이그레이션이 필요하다.

---

## COM-003. production MongoDB URI scheme 검증 부족

### 우선순위

**P1 — 잘못된 운영 설정이 runtime까지 진행될 수 있음**

### 관련 구현

- [config.py:226](C:/encore_first_project/src/common/config.py:226): 명시적 MongoDB URI 선택
- [config.py:244-250](C:/encore_first_project/src/common/config.py:244): production credential 검사
- [faq.py:77](C:/encore_first_project/src/loading/faq.py:77): URI를 `MongoClient`에 전달

### 확인 결과

다음 production 설정이 `Settings.from_env()` 단계에서 허용됐다.

```text
APP_ENV=production
SQL_HOST=sql
SQL_USER=sql-user
SQL_PASSWORD=sql-pass
MONGODB_URI=http://mongo-user:mongo-pass@mongo-1:27017/db
```

현재 검증은 URI의 username/password 존재 여부만 확인하고 `mongodb://` 또는 `mongodb+srv://` scheme인지 확인하지 않는다. 이후 PyMongo가 해당 URI를 처리할 때 실패할 가능성이 있다.

### 영향

- 배포 시작 전 설정 오류가 조기에 차단되지 않는다.
- pipeline 실행 시점에야 MongoDB 연결 실패가 발생할 수 있다.

### 승인 기준

- 허용 scheme과 host 목록 형식을 명시한다.
- 잘못된 scheme, 빈 host, 잘못된 port, Replica Set query 누락 여부를 production 설정 단계에서 검증할지 결정한다.
- 결정된 계약을 테스트 파일에 저장한다.

본 보고서에서는 수정하지 않았다.

---

## COM-004. 명시적 URI와 별도 MongoDB 인증정보 계약 충돌

### 우선순위

**P1 — 인증정보가 설정에 존재해도 실제 연결에 사용되지 않을 수 있음**

### 확인 결과

다음 설정도 `Settings.from_env()`에서 허용됐다.

```text
MONGODB_URI=mongodb://mongo-1:27017/db?replicaSet=rs0
MONGODB_USER=mongo-user
MONGODB_PASSWORD=mongo-pass
```

그러나 [config.py:287](C:/encore_first_project/src/common/config.py:287)는 명시적 URI를 그대로 `settings.mongo_uri`에 보존하고, [faq.py:77](C:/encore_first_project/src/loading/faq.py:77)는 `settings.mongo_uri`만 `MongoClient`에 전달한다. 별도 `mongo_user`와 `mongo_password`는 URI에 합쳐지지 않는다.

### 영향

- 설정 검증은 성공하지만 실제 MongoDB 인증이 실패할 수 있다.
- 운영자는 인증정보가 적용됐다고 오판할 수 있다.

### 승인 기준

다음 중 하나를 명시적으로 선택해야 한다.

1. production에서는 인증정보를 항상 전체 MongoDB URI 안에 포함한다.
2. URI에 인증정보가 없으면 `MONGODB_USER/PASSWORD`를 이용해 URI를 조합한다.
3. URI와 별도 인증정보를 함께 받지 않고 설정 단계에서 거부한다.

MongoDB URI를 전달받은 뒤 실제 연결 방식과 함께 확정해야 한다.

---

## COM-005. Replica Set 전체 URI 및 실제 DB 연결 검증 보류

### 우선순위

**P1-조건부 — URI 전달 전 검증 불가**

### 현재 상태

루트 `.env`는 현재 `APP_ENV=local`이고 `MONGODB_URI`가 비어 있다. 따라서 현재 로컬 설정은 `mongodb://localhost:27017/` fallback을 사용하며, Replica Set 전체 URI 계약을 실행하지 않는다.

전체 host 목록과 `replicaSet` 옵션을 포함한 임시 URI를 mock `MongoClient`에 전달하는 검사는 통과했다. 하지만 실제 MongoDB 서버에 대한 다음 검사는 아직 하지 못했다.

- `ping` 및 server selection
- Primary 발견
- Secondary 구성원 discovery
- `replicaSet` 이름 일치
- authentication source·사용자 권한
- failover 이후 재선택

### 승인 기준

MongoDB URI를 전달받은 뒤 비밀값을 로그에 남기지 않는 별도 연결 검증을 수행해야 한다. 최소한 URI host 수, `replicaSet` query, 연결 대상 database, `ping` 결과와 server description을 확인해야 한다.

URI가 전달되기 전까지 MongoDB 적재 모듈의 production 동작을 승인하지 않는다.

---

## COM-006. `RunContext` reference source와 문서 signature 차이

### 우선순위

**P1-조건부 — positional 호출자 존재 여부 확인 필요**

### 비교 결과

현재 구현은 다음 순서다.

```python
RunContext(run_id, pipeline_name, schedule_name, started_at)
```

- [현재 contracts.py:49-53](C:/encore_first_project/src/common/contracts.py:49)
- 레퍼런스 문서 `docs/00_implementation.md:227-231`도 `schedule_name` 후 `started_at` 순서

하지만 레퍼런스 소스는 다음과 다르다.

- `C:\encore_first_project\ref\mlo-01-p1-team3-a\src\common\contracts.py:54-58`
- `RunContext(run_id, pipeline_name, started_at, schedule_name=None)`

### 영향

레퍼런스 소스 기준으로 positional 생성하거나 `schedule_name`을 생략한 호출자는 현재 구현에서 `TypeError` 또는 값 위치 오해가 발생할 수 있다.

### 승인 기준

문서와 reference source 중 어떤 signature를 SSOT로 사용할지 결정하고, positional·keyword 호출 테스트를 추가해야 한다.

---

## COM-007. 로그 마스킹의 일반 `key` 과잉 매칭

### 우선순위

**P2 — 보안 누출은 막지만 로그 데이터가 변형될 수 있음**

### 관련 구현

- [logging_utils.py:13-14](C:/encore_first_project/src/common/logging_utils.py:13)
- [logging_utils.py:31](C:/encore_first_project/src/common/logging_utils.py:31)

### 확인 결과

현재 정규식은 일반 단어 `key`를 경계 없이 검색한다.

```text
redact("monkey=banana")
→ "monkey=[REDACTED]"
```

실제 API key, password, URI 등은 마스킹되지만 `monkey`, `hockey`처럼 정상 필드명이 포함된 문자열도 변형될 수 있다.

### 영향

- 로그 검색·분석 시 원문 값이 보존되지 않는다.
- 비밀정보 보호와 정상 데이터 보존 사이의 계약이 불명확하다.

### 승인 기준

`key` 단독 매칭을 허용할지, `api_key`, `x-api-key`, `*_key`처럼 경계가 있는 이름만 보호할지 결정하고 redaction regression test를 저장해야 한다.

---

## COM-008. README의 host 하드코딩 설명과 fallback 코드 불일치

### 우선순위

**P2 — 문서 정합성 문제**

### 확인 결과

README는 [common/README.md:38](C:/encore_first_project/src/common/README.md:38)에서 API key, DB password, host를 하드코딩하지 않는다고 설명한다.

그러나 config에는 다음 fallback 값이 있다.

- [config.py:176](C:/encore_first_project/src/common/config.py:176): `http://192.168.0.51:4000`
- [config.py:153-154](C:/encore_first_project/src/common/config.py:153): `mongodb://localhost:27017/`, `localhost`
- [config.py:215](C:/encore_first_project/src/common/config.py:215): MongoDB host `localhost` fallback

이 값들이 운영 host를 강제하는 것은 아니지만, “host를 하드코딩하지 않는다”는 문장과는 일치하지 않는다.

### 승인 기준

fallback을 의도된 local default로 인정한다면 README를 그 의미에 맞게 표현해야 한다. 운영 환경에서 반드시 외부 주입해야 한다면 production 검증과 문서에 그 조건을 명시해야 한다.

---

## COM-009. 실제 외부 API·MySQL·MongoDB 검증 부재

### 우선순위

**P1-조건부 — fixture/mock만으로 운영 승인 불가**

### 확인 결과

레퍼런스 테스트 `16 passed`는 JSON fixture와 JSONL sink 중심이며 실제 운영 DB connection을 열지 않는다. 공통 모듈 직접 검사도 표준 Python 객체와 mock MongoClient 수준이다.

따라서 다음은 검증되지 않았다.

- MySQL authentication 및 실제 SQL DATETIME/DATE binding
- MySQL Primary 적재 이후 Replica 적용 상태
- MongoDB Replica Set Primary 선택 및 write concern
- 외부 API의 실제 응답 schema·quota·timeout
- bastion/NAT/private subnet 경로

### 승인 기준

운영과 동일한 비밀 주입 방식 및 비운영 fixture를 사용한 통합 검증 환경을 별도로 마련해야 한다. 실제 secret은 테스트 로그와 report에 기록하지 않는다.

---

## COM-010. project root 외부 import 경로 조건

### 우선순위

**P2-조건부 — 문서화된 실행 방식 밖에서만 재현**

### 확인 결과

`PYTHONPATH=C:\encore_first_project\src`를 지정하면 다음 canonical import가 정상이다.

```python
from common.logging_utils import JsonlLogger, redact
```

project root만 제공하고 `src`를 Python path에 추가하지 않으면 `common` 패키지를 찾지 못한다. 이는 wrapper 의존성 문제가 아니라 배포 시 `src`를 설치하거나 `PYTHONPATH`에 포함해야 하는 패키징 조건이다.

### 승인 기준

배포 실행 방식이 `PYTHONPATH=...\\src` 기준인지 package 설치 방식인지 확정하고 그 방식의 import smoke test를 저장해야 한다.

---

## 3. 보안 및 환경 관찰사항

- 루트 `.env`는 `.gitignore` 대상이며 이번 검사에서 secret 값은 출력하지 않았다.
- `.env`에는 실제 registration API key가 존재하므로, 파일이 외부에 공유되었거나 commit된 이력이 있으면 key 교체가 필요하다.
- 현재 `.env`의 `MONGODB_URI`는 비어 있으므로 Replica Set 운영값이 주입되기 전까지 local fallback으로만 동작한다.
- 이번 보고서 작성 중 `.env`, 소스, 테스트 파일은 수정하지 않았다.

## 4. 최종 판정

`src/common`의 파일 구조·public export·stage 경계·`.env` key 이름은 현재 작업 트리 기준으로 정합하다. 그러나 공통 전용 테스트 파일이 없어 검증 증거가 저장소에 남아 있지 않고, production MongoDB URI 계약·실제 Replica Set 연결·reference `RunContext` signature가 확정되지 않았다.

따라서 현재 판정은 다음과 같다.

```text
공통 모듈 문법 및 fixture 수준 동작: 통과
공통 모듈 검수 완료: 보류
production MongoDB 적재 승인: URI 전달 및 실제 연결 검증 전 보류
```

## 5. 다음 확인 순서

1. MongoDB Replica Set 전체 URI와 인증 계약을 전달한다.
2. COM-003·COM-004의 production URI/credential 정책을 확정한다.
3. `src/common` 전용 테스트 파일을 저장소에 추가하고 clean checkout에서 재실행한다.
4. `RunContext`의 문서·reference source·상위 호출자 signature를 하나로 확정한다.
5. mock을 넘어 실제 비운영 MySQL/MongoDB 연결 smoke test를 수행한다.

