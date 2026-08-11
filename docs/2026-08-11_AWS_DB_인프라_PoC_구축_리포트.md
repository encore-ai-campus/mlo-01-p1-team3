# AWS 기반 데이터 수집·DB 이중화 PoC 구축 리포트

- **프로젝트:** 자동차 렌탈·리스 기업 시장 분석 솔루션
- **작업일:** 2026-08-11
- **구축 목적:** AWS VPC 환경에서 Public/Private 네트워크를 구성하고, Collector 서버와 MySQL/MongoDB 서버를 분리하여 실제 데이터 수집·저장 구조의 기반을 검증한다.
- **구축 범위:** VPC, Subnet, Route Table, Internet Gateway, NAT Gateway, Bastion, Collector, MySQL 이중화, MongoDB Replica Set
- **비고:** 학원 제공 AWS 계정에서 단일 계정 PoC 형태로 우선 구축

---

## 1. 작업 개요

이번 작업에서는 실제 프로젝트에 적용할 AWS 인프라 구조를 단일 AWS 계정에서 먼저 구현하였다.

주요 목표는 다음과 같다.

1. Public Subnet과 Private Subnet을 분리한다.
2. Bastion Host를 통해서만 Private EC2에 SSH 접근할 수 있도록 구성한다.
3. Collector 서버는 Public IP 없이 Private Subnet에서 운영한다.
4. Collector가 공공데이터 API 및 외부 웹사이트에 접근할 수 있도록 NAT Gateway를 통한 Outbound 통신을 검증한다.
5. MySQL을 EC2에 직접 설치하여 Primary/Secondary 복제를 구성한다.
6. MongoDB를 EC2 3대에 설치하여 Replica Set을 구성한다.
7. DB 복제 동작을 실제 데이터 입력/조회로 검증한다.
8. 테스트 완료 후 불필요한 AWS 리소스를 삭제하거나 중지하여 비용을 최소화한다.

---

## 2. 최종 구성

### 2.1 VPC

| 항목 | 설정 |
|---|---|
| VPC Name | `car-market-vpc` |
| CIDR | `10.0.0.0/16` |
| Region | Seoul (`ap-northeast-2`) |

### 2.2 Subnet

| Subnet | CIDR | AZ | 용도 |
|---|---|---|---|
| `car-public-a` | `10.0.1.0/24` | `ap-northeast-2a` | Bastion, NAT Gateway |
| `car-private-a` | `10.0.10.0/24` | `ap-northeast-2a` | Collector, MySQL Primary, MongoDB |
| `car-private-c` | `10.0.20.0/24` | `ap-northeast-2c` | MySQL Secondary, MongoDB |

Public Subnet에는 Public IPv4 자동 할당을 활성화하였고, Private Subnet의 EC2에는 Public IP를 할당하지 않았다.

---

## 3. 네트워크 구성

### 3.1 Internet Gateway

- Internet Gateway 생성
- VPC `car-market-vpc`에 연결
- Public Route Table의 기본 경로로 사용

### 3.2 Public Route Table

**Name:** `car-public-rt`

| Destination | Target |
|---|---|
| `10.0.0.0/16` | local |
| `0.0.0.0/0` | Internet Gateway |

연결 Subnet:

- `car-public-a`

### 3.3 Private Route Table

Private Subnet용 Route Table을 별도로 생성하였다.

NAT Gateway 운영 중에는 다음 경로를 사용하였다.

| Destination | Target |
|---|---|
| `10.0.0.0/16` | local |
| `0.0.0.0/0` | NAT Gateway |

Private Subnet을 Public Route Table과 분리함으로써 Private EC2가 Internet Gateway에 직접 노출되지 않도록 구성하였다.

---

## 4. NAT Gateway 구성 및 검증

Private Subnet의 Collector 및 DB 서버에서 패키지 설치와 외부 API 접근이 필요했기 때문에 일시적으로 NAT Gateway를 구성하였다.

### 설정

- Availability Mode: **Zonal**
- Subnet: `car-public-a`
- Connectivity Type: **Public**
- Elastic IP 할당

### 검증

Collector 서버에서 외부 통신을 확인하였다.

- HTTP 요청 → **HTTP 200 응답 확인**
- 외부 IP Ping → **정상 응답 확인**

따라서 아래 흐름의 Outbound 통신이 정상임을 확인하였다.

```text
Private EC2
    ↓
Private Route Table
    ↓
NAT Gateway
    ↓
Internet Gateway
    ↓
Internet
```

MongoDB 및 MySQL 패키지 설치 완료 후 비용 절감을 위해 다음 작업을 수행하였다.

- NAT Gateway 삭제
- NAT Gateway용 Elastic IP Release
- Private Route Table의 NAT 기본 경로 정리

---

## 5. Bastion Host 구성

### 역할

외부 사용자가 Private Subnet의 EC2에 직접 접근하지 않고 Bastion Host를 거쳐 관리 서버에 접근하도록 구성하였다.

```text
사용자 PC
   ↓ SSH
Bastion Host
   ↓ SSH
Private EC2
```

### 주요 설정

- Name: `car-bastion`
- Subnet: `car-public-a`
- Private IP: `10.0.1.10`
- Public IPv4: 사용
- Key Pair: `encore_student_key`
- Security Group: `car-bastion-sg`

Bastion Security Group은 SSH(22)를 현재 작업 환경의 Public IP `/32`에서만 허용하도록 구성하였다.

Windows에서 PEM 파일 ACL 문제로 최초 SSH 접속 오류가 발생하였으나, 파일 권한을 수정한 후 정상 접속을 확인하였다.

---

## 6. Private EC2 접근 정책

Private EC2에는 공통 Security Group `car-private-sg`를 적용하였다.

### 기본 SSH 정책

| Type | Port | Source |
|---|---:|---|
| SSH | 22 | `car-bastion-sg` |

Private EC2는 Public IP를 사용하지 않으며 Bastion Security Group에서 들어오는 SSH 요청만 허용하였다.

실습 편의를 위해 Bastion에 PEM 키를 임시 저장하여 Private EC2로 접속하였다.

> 실제 운영 환경에서는 Bastion에 Private Key를 직접 보관하기보다 AWS Systems Manager Session Manager, SSH Agent Forwarding, ProxyJump 등의 방식을 검토하는 것이 적절하다.

---

## 7. Collector 서버

### 설정

- Name: `car-collector`
- Subnet: `car-private-a`
- Private IP: `10.0.10.10`
- Public IP: 없음
- Security Group: `car-private-sg`

### 검증

1. 사용자 PC → Bastion 접속 성공
2. Bastion → Collector SSH 접속 성공
3. NAT Gateway 구성 후 Collector → Internet 통신 성공

최종 프로젝트에서는 Collector에서 다음 작업을 수행할 예정이다.

- 자동차 등록 공공데이터 수집
- 기업 FAQ 크롤링
- 데이터 전처리
- 결측·중복·형식 오류 검증
- MySQL/MongoDB 적재
- cron 또는 APScheduler 기반 자동 실행

---

## 8. MySQL 서버 구성

MySQL은 Amazon RDS를 사용하지 않고 EC2에 직접 설치하였다.

### 8.1 서버 구성

| 역할 | Private IP | Subnet |
|---|---|---|
| MySQL Primary | `10.0.10.20` | `car-private-a` |
| MySQL Secondary | `10.0.20.20` | `car-private-c` |

두 인스턴스 모두 동일한 Key Pair를 지정하였으며 Public IP는 할당하지 않았다.

### 8.2 MySQL 설치

두 서버에 MySQL Community Server를 설치하고 다음 작업을 수행하였다.

- 시스템 패키지 업데이트
- MySQL 설치
- `mysqld` 서비스 시작
- 부팅 시 자동 시작 활성화
- 임시 root 비밀번호 확인
- root 비밀번호 변경

### 8.3 Primary 설정

`/etc/my.cnf`

```ini
[mysqld]
server-id=1
log_bin=mysql-bin
```

### 8.4 Secondary 설정

`/etc/my.cnf`

```ini
[mysqld]
server-id=2
relay-log=relay-bin
read_only=ON
```

설정 변경 후 두 서버의 `mysqld`를 재시작하였다.

### 8.5 MySQL 통신 허용

Security Group에 MySQL 통신 규칙을 추가하였다.

| Type | Port | Source |
|---|---:|---|
| MySQL/Aurora | 3306 | `car-private-sg` |

동일 Security Group을 Source로 지정하여 해당 SG가 적용된 EC2 간 MySQL 통신을 허용하였다.

---

## 9. MySQL Replication 구성

Primary에 복제 전용 계정을 생성하고 Secondary가 Primary의 Binary Log를 읽도록 구성하였다.

### Primary Binary Log 확인

MySQL 8.4에서는 기존 `SHOW MASTER STATUS` 대신 다음 명령을 사용하였다.

```sql
SHOW BINARY LOG STATUS;
```

확인 결과:

```text
File     : mysql-bin.000001
Position : 868
```

### 인증 문제 발생

초기 복제 연결 시 다음 오류가 발생하였다.

```text
Authentication plugin 'caching_sha2_password' reported error:
Authentication requires secure connection.
```

MySQL 8.4의 기본 인증 방식인 `caching_sha2_password`에서 비암호화 복제 연결 시 RSA Public Key 교환이 필요하여 다음 옵션을 추가하였다.

```sql
GET_SOURCE_PUBLIC_KEY=1
```

### 최종 복제 상태

복제 상태 확인 결과:

```text
Replica_IO_Running: Yes
Replica_SQL_Running: Yes
```

으로 정상 연결됨을 확인하였다.

### 데이터 복제 검증

Primary에서 생성한 DB/테이블 및 데이터가 Secondary에서 정상 조회되는 것을 확인하였다.

**결과: MySQL Primary → Secondary 복제 정상**

---

## 10. MongoDB 서버 구성

### 10.1 서버 구성

| 역할 | Private IP | Subnet |
|---|---|---|
| MongoDB Node 1 | `10.0.10.30` | `car-private-a` |
| MongoDB Node 2 | `10.0.20.30` | `car-private-c` |
| MongoDB Node 3 | `10.0.10.31` | `car-private-a` |

총 3대의 MongoDB EC2를 구성하였다.

### 10.2 MongoDB 설치

세 서버 모두 MongoDB Community Server를 설치하고 다음을 수행하였다.

- MongoDB Repository 설정
- `mongodb-org` 설치
- `mongod` 서비스 시작
- 부팅 시 자동 시작 활성화

---

## 11. MongoDB Replica Set 구성

세 서버의 `/etc/mongod.conf`를 수정하였다.

예시:

```yaml
net:
  port: 27017
  bindIp: 127.0.0.1,10.0.10.30

replication:
  replSetName: "rs0"
```

각 노드는 자신의 Private IP를 `bindIp`에 설정하였다.

### MongoDB 통신 허용

Security Group에 다음 규칙을 추가하였다.

| Type | Port | Source |
|---|---:|---|
| Custom TCP | 27017 | `car-private-sg` |

### 설정 오류

MongoDB 설정 과정에서 YAML 문법 오류가 발생하였다.

```text
Error parsing YAML config file
```

원인은 설정 파일의 들여쓰기/문법 문제였으며 수정 후 `mongod` 서비스가 정상적으로 `active (running)` 상태가 되는 것을 확인하였다.

### Replica Set 초기화

MongoDB Node 1에서 Replica Set을 초기화하였다.

```javascript
rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "10.0.10.30:27017" },
    { _id: 1, host: "10.0.20.30:27017" },
    { _id: 2, host: "10.0.10.31:27017" }
  ]
})
```

초기 시도 중 `10.0.20.30:27017`의 `Connection refused` 오류가 발생하였으나 해당 노드의 설정 및 서비스 상태를 수정한 후 정상 연결되었다.

최종적으로 3개 노드가 다음 형태로 구성된 것을 확인하였다.

```text
PRIMARY
SECONDARY
SECONDARY
```

### 복제 검증

Primary에서 테스트 데이터를 생성하고 Secondary에서 데이터를 조회하여 3대 모두 정상적으로 Replica Set이 동작하는 것을 확인하였다.

**결과: MongoDB 3-Node Replica Set 정상**

---

## 12. 최종 EC2 구성 현황

| 서버 | 수량 | 역할 |
|---|---:|---|
| Bastion | 1 | Private 서버 관리 접점 |
| Collector | 1 | API/크롤링/ETL |
| MySQL | 2 | 정형 데이터 저장 및 복제 |
| MongoDB | 3 | FAQ 저장 및 Replica Set |
| **합계** | **7** | |

향후 Monitoring/Dashboard 서버 1대를 추가하면 전체 설계는 EC2 8대 구성이 된다.

---

## 13. 비용 절감 조치

학원 제공 AWS 계정의 제한된 크레딧을 고려하여 다음 비용 절감 조치를 수행하였다.

- EC2는 실습 목적의 소형 인스턴스 사용
- DB 서버는 RDS 대신 EC2 직접 설치
- NAT Gateway는 패키지 설치 및 인터넷 연결 검증 동안에만 임시 운영
- 테스트 완료 직후 NAT Gateway 삭제
- NAT Gateway에서 사용한 Elastic IP Release
- 작업 종료 후 EC2 7대 모두 Stop 명령 수행

EC2 중지 후에도 EBS 등의 저장 리소스 비용은 일부 발생할 수 있으므로 추후 비용 모니터링이 필요하다.

---

## 14. 트러블슈팅 내역

| 문제 | 원인 | 해결 |
|---|---|---|
| Windows에서 Bastion SSH 접속 실패 | PEM 파일 ACL 권한 문제 | Windows 파일 권한 수정 |
| Collector에서 Internet 접근 불가 | Private Subnet에 NAT 경로 없음 | NAT Gateway + Private Route 설정 |
| MySQL `SHOW MASTER STATUS` 오류 | MySQL 8.4에서 명령 변경 | `SHOW BINARY LOG STATUS` 사용 |
| MySQL Replica IO Connecting | `caching_sha2_password` 인증 요구 | `GET_SOURCE_PUBLIC_KEY=1` 추가 |
| MongoDB 시작 실패 | `mongod.conf` YAML 문법 오류 | 설정 파일 문법 수정 |
| MongoDB Replica Set 초기화 실패 | 일부 노드의 27017 Connection refused | 해당 노드 bindIp/service 상태 수정 |
| Secondary MongoDB 조회 혼선 | Secondary Read Preference 설정 필요 | Secondary 읽기 설정 후 조회 |

---

## 15. 검증 결과

| 검증 항목 | 결과 |
|---|---|
| 사용자 PC → Bastion SSH | ✅ 성공 |
| Bastion → Collector SSH | ✅ 성공 |
| Bastion → MySQL SSH | ✅ 성공 |
| Bastion → MongoDB SSH | ✅ 성공 |
| Private EC2 → Internet via NAT | ✅ 성공 |
| MySQL Primary → Secondary Replication | ✅ 성공 |
| MySQL 데이터 복제 | ✅ 성공 |
| MongoDB 3-Node Replica Set | ✅ 성공 |
| MongoDB 데이터 복제 | ✅ 성공 |
| NAT Gateway 삭제 | ✅ 완료 |
| NAT용 Elastic IP 해제 | ✅ 완료 |
| EC2 7대 중지 | ✅ 완료 |

---

## 16. 현재 데이터 흐름

```text
                  Internet
                     │
            ┌────────┴────────┐
            │                 │
     공공데이터 API       기업 FAQ Web
            │                 │
            └────────┬────────┘
                     │
                  Collector
                 10.0.10.10
                 /          \
                /            \
               ▼              ▼
        MySQL Primary     MongoDB Replica Set
         10.0.10.20       10.0.10.30
              │            10.0.20.30
              ▼            10.0.10.31
        MySQL Secondary
         10.0.20.20
```

관리 접근은 다음 경로를 사용한다.

```text
관리자 PC
   │
   ▼
Bastion
10.0.1.10
   │
   ├── Collector
   ├── MySQL Primary
   ├── MySQL Secondary
   └── MongoDB Nodes
```

---

## 17. 다음 작업 계획

다음 작업에서는 단일 계정에서 검증한 구조를 4명의 팀원 AWS 계정으로 분리할 예정이다.

예상 역할은 다음과 같다.

| AWS 계정 | 역할 |
|---|---|
| Account 1 | Collector |
| Account 2 | MySQL Primary / Secondary |
| Account 3 | MongoDB Replica Set |
| Account 4 | Bastion / Monitoring |

계정 간 통신은 **VPC Peering**을 이용할 예정이며, 각 VPC CIDR은 겹치지 않도록 설계해야 한다.

추가 예정 작업:

- 4개 AWS 계정 VPC 구성
- VPC Peering 연결
- Peering Route Table 설정
- Security Group 접근 정책 재설계
- Collector → MySQL/MongoDB 연결 테스트
- 실제 자동차 등록 데이터 수집/적재
- FAQ 크롤링 및 MongoDB 적재
- 데이터 품질 검증
- cron/APScheduler 자동화
- Monitoring/Dashboard 서버 구축
- 실행 로그 및 오류 알림 구현
- AWS CLI 기반 인프라 자동 생성 스크립트 작성

---

## 18. 작업 결론

단일 AWS 계정 환경에서 실제 프로젝트의 핵심 인프라를 PoC 형태로 구현하였다.

Public/Private Subnet을 분리하고 Bastion을 통한 관리 접근 구조를 구축했으며, Collector 서버의 Internet Outbound 통신을 NAT Gateway를 통해 검증하였다.

데이터 저장 영역에서는 MySQL Primary/Secondary 복제와 MongoDB 3-Node Replica Set을 직접 EC2에 구축하여 실제 데이터 복제까지 확인하였다.

이를 통해 향후 4개 AWS 계정으로 인프라를 분산하기 전에 네트워크 구조, DB 통신, 복제 설정 및 보안 정책의 기본 동작을 사전에 검증하였다.

**최종 결과: AWS 네트워크 기본 구성 및 MySQL/MongoDB 이중화 PoC 구축 성공**
