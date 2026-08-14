# 로컬 리소스 로그 아카이브 검증 보고서

## 1. 목적

Collector, MySQL Primary/Secondary, MongoDB 01/02/03의 공통 시스템 자원 로그
`/var/log/car-market/resource.log`를 시간별로 회전하고, 일 1회 Monitoring 서버에
역할별로 분리 보관하는 shell 운영 모듈을 AWS 연결 없이 검증했다.

대상 운영 파일은 [ops/logging](../../ops/logging)이다.

## 2. 실행 일시 및 환경

| 항목 | 값 |
|---|---|
| 검증 일시 | 2026-08-13 (Asia/Seoul) |
| 실행 위치 | `C:\encore_first_project` |
| Shell | Git for Windows Bash |
| 외부 네트워크 | 사용하지 않음 |
| AWS EC2 | 사용하지 않음 |
| 테스트 파일 | [tests/test_ops_logging.sh](../../tests/test_ops_logging.sh) |

실행 명령:

```bash
bash -n ops/logging/*.sh tests/test_ops_logging.sh
bash tests/test_ops_logging.sh
```

실행 결과:

```text
PASS: six-source hourly rotation and daily Monitoring archive workflow
```

## 3. 검증 결과

| 검증 항목 | 결과 | 확인 내용 |
|---|---|---|
| Bash 문법 | 통과 | 운영 shell 5개와 테스트 shell 1개를 `bash -n`으로 검사 |
| 6개 역할 디렉터리 | 통과 | `collector`, `mysql-primary`, `mysql-secondary`, `mongo-01`, `mongo-02`, `mongo-03`의 staging/archive/quarantine 디렉터리 생성 확인 |
| 시간별 회전 호출 | 통과 | 전용 logrotate state와 설정 파일을 launcher가 올바르게 전달하는지 확인 |
| Collector 전송 성공 | 통과 | gzip 파일을 source staging으로 전달하고 소스 파일을 성공 후 삭제하는지 확인 |
| 역할별 최종 적재 | 통과 | 6개 역할의 파일이 서로 다른 Monitoring archive 디렉터리에 저장되는지 확인 |
| 전송 실패 재시도 | 통과 | rsync 실패 시 소스 gzip 파일 유지, `pending_count=1`, 실패 상태 로그 기록 확인 |
| 손상 gzip 처리 | 통과 | `gzip -t` 실패 파일을 final archive가 아닌 source별 quarantine으로 이동 확인 |
| 동일 이름 충돌 | 통과 | 동일 이름·다른 내용 파일을 quarantine으로 보내고 기존 archive를 보존하는지 확인 |
| 허용되지 않은 역할 | 통과 | 6개 계약 외 `SOURCE_ID`는 전송 전에 실패하는지 확인 |
| 다중 hard link 차단 | 통과 | 다중 hard link 파일을 quarantine으로 이동하고 final archive에 적재하지 않는지 확인 |

## 4. 로컬 검증 범위 밖 항목

다음은 AWS EC2에서 smoke test로 확인해야 하며, 이번 로컬 검증에서는 확인하지 않았다.

| 항목 | 확인 방법 |
|---|---|
| 실제 SSH 키 인증 | 소스 EC2에서 `logship@10.0.10.40` SSH 연결 테스트 |
| Security Group / NACL | 소스 6대에서 Monitoring TCP 22 연결 확인 |
| 실제 rsync 전송 | 소스의 회전 gzip 파일을 Monitoring staging으로 전송 |
| 실제 logrotate 동작 | `logrotate -d` 후 승인된 1회 강제 회전 smoke test |
| cron 실행 | `/etc/cron.d/` 설치 후 `crond` 상태 및 실행 로그 확인 |
| 파일 권한/소유자 | `logship`이 staging에만 쓰고 final archive는 root가 관리하는지 확인 |
| 디스크 용량/보존 정책 | 소스 7일 안전망과 Monitoring 최종 보관 기간 결정 |

## 5. 결론

로컬 shell 모듈은 문법 및 주요 운영 계약을 모두 통과했다. 따라서 AWS 적용 전 코드 수준의 검증은 완료 상태다.

다만 실제 EC2 네트워크·권한·cron은 로컬에서 대체할 수 없으므로, 운영 전에는 Monitoring 1대와 Collector 1대를 대상으로 1회 end-to-end smoke test를 먼저 수행해야 한다. 그 성공 후 MySQL 2대와 MongoDB 3대에 같은 설정을 확대 적용하는 순서를 권장한다.
