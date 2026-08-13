# Git Flow 전략

## 1. 기본 원칙

- `main` 브랜치는 운영 환경에 배포된 버전과 일치하며, 항상 실행 및 배포 가능한 상태를 유지한다.
- `develop` 브랜치는 다음 릴리스를 위한 통합 브랜치다. 일상적인 기능 개발 결과는 우선 `develop`에 통합한다.
- `main`과 `develop`에서의 직접 작업, 직접 커밋, 직접 push는 엄격히 금지한다. 모든 변경사항은 Pull Request(PR)를 통해 반영한다.
- 일반적인 기능 개발 및 수정 브랜치는 최신 `develop`에서 생성하고, 작업이 끝나면 `develop`을 대상으로 PR을 생성한다.
- `release` 브랜치는 `develop`에서 생성하여 출시 준비와 안정화에만 사용한다. 안정화가 끝나면 `main`과 `develop` 양쪽에 반영한다.
- `hotfix` 브랜치는 운영 중인 버전을 기준으로 `main`에서 생성한다. 긴급 수정 후 `main`과 `develop` 양쪽에 반영한다.
- 하나의 브랜치에서는 하나의 이슈 또는 하나의 목적만 다룬다.
- 이미 공유된 커밋의 이력을 변경하지 않는다. 팀의 병합 방식은 merge commit으로 통일하며, 공유 브랜치에서 rebase와 force push는 사용하지 않는다.
- 운영 배포가 완료된 `main`의 커밋에는 버전 태그를 생성한다.

## 2. 브랜치 규칙

Git Flow에서는 역할이 고정된 장기 브랜치와 목적별 단기 브랜치를 구분하여 사용한다.

### 2.1 장기 브랜치

| 브랜치 | 용도 |
| --- | --- |
| `main` | 운영 환경에 배포된 안정 버전 관리 |
| `develop` | 다음 릴리스에 포함될 변경사항 통합 |

- `main`과 `develop`은 직접 push하지 않고 PR로만 변경한다.
- `main`에는 운영 배포가 완료된 버전만 반영한다.
- `develop`은 다음 릴리스의 기준 브랜치이므로, 기능 개발 결과를 먼저 통합하고 릴리스 시점을 관리한다.

### 2.2 작업 브랜치

일반적인 브랜치 이름은 다음 형식을 사용한다.

```text
<type>/<issue-number>-<short-description>
```

`release` 브랜치는 버전으로 이름을 정한다.

```text
release/<version>
```

브랜치 이름에는 영문 소문자와 하이픈(`-`)을 사용하고, `release`를 제외한 작업 브랜치에는 이슈 번호를 포함한다. 브랜치 접두사에는 슬래시(`/`)를 사용한다.

| 접두사 | 용도 | 생성 기준 | 기본 병합 대상 | 예시 |
| --- | --- | --- | --- | --- |
| `feature/` | 새로운 기능 개발 | `develop` | `develop` | `feature/12-login` |
| `bugfix/` | 개발 중인 일반 버그 수정 | `develop` | `develop` | `bugfix/24-login-validation` |
| `release/` | 릴리스 준비, 최종 테스트 및 안정화 | `develop` | `main`, `develop` | `release/v1.0.0` |
| `hotfix/` | 운영 중인 버전의 긴급 오류 수정 | `main` | `main`, `develop` | `hotfix/31-payment-error` |
| `docs/` | 문서 작성 및 수정 | `develop` | `develop` | `docs/7-git-flow` |
| `refactor/` | 기능 변경 없는 코드 개선 | `develop` | `develop` | `refactor/18-user-service` |
| `test/` | 테스트 추가 및 수정 | `develop` | `develop` | `test/22-order-service` |
| `chore/` | 설정, 의존성 등 기타 작업 | `develop` | `develop` | `chore/5-update-dependency` |

- `feature/`, `bugfix/`, `docs/`, `refactor/`, `test/`, `chore/` 브랜치에는 새로운 기능이나 수정사항을 목적에 맞게만 포함한다.
- `release/` 브랜치에는 새로운 기능을 추가하지 않는다. 릴리스에 필요한 버그 수정, 문서, 버전 및 설정 변경만 허용한다.
- `hotfix/` 브랜치는 긴급한 운영 장애나 치명적인 버그에만 사용한다.

## 3. 커밋 메시지 규칙

모든 커밋은 변경 목적을 알 수 있는 접두사를 사용한다. 커밋 메시지의 접두사에는 브랜치와 달리 콜론(`:`)을 사용한다.

```text
<type>: <summary>
```

| 접두사 | 용도 |
| --- | --- |
| `feat` | 새로운 기능 추가 |
| `fix` | 버그 수정 |
| `docs` | 문서 변경 |
| `refactor` | 리팩토링 |
| `test` | 테스트 변경 |
| `chore` | 빌드, 설정, 의존성 등 기타 변경 |
| `style` | 포맷팅 및 코드 스타일 변경 |
| `perf` | 성능 개선 |
| `merge` | 브랜치 병합 및 충돌 해결을 위한 병합 커밋 |

예시:

```text
feat: 로그인 기능 추가
fix: 잘못된 비밀번호 검증 수정
docs: Git Flow 전략 문서화
test: 주문 서비스 단위 테스트 추가
merge: develop 최신 변경사항 반영
```

- 하나의 커밋에는 하나의 논리적인 변경만 포함한다.
- `수정`, `완료`, `작업`처럼 변경 내용을 알 수 없는 메시지는 사용하지 않는다.
- 병합 커밋은 `merge:` 형식을 사용하거나 Git/GitHub가 생성한 병합 메시지를 그대로 사용한다.
- 커밋에 비밀번호, API 키, 개인정보 등 민감한 정보를 포함하지 않는다.

## 4. 작업 흐름

### 4.1 이슈 확인 및 작업 브랜치 생성

작업을 시작하기 전에 관련 이슈를 확인하고 담당자를 지정한다. 이후 최신 `develop`에서 작업 브랜치를 생성한다.

```bash
git fetch origin
git switch develop
git pull --no-rebase origin develop
git switch -c feature/12-login
```

작업 유형에 따라 `feature/` 대신 `bugfix/`, `docs/`, `refactor/`, `test/`, `chore/` 등의 접두사를 사용한다.

### 4.2 작업 및 커밋

변경사항을 작은 단위로 나누어 작업하고, 의미 있는 단위마다 커밋한다.

```bash
git add <변경한-파일>
git commit -m "feat: 로그인 기능 추가"
git push -u origin feature/12-login
```

### 4.3 기능·일반 수정 PR 생성

작업 브랜치를 push한 뒤 base 브랜치를 `develop`으로 지정하여 PR을 생성한다. PR에는 다음 내용을 포함한다.

- 변경 목적과 주요 변경사항
- 관련 이슈 링크 또는 이슈 번호
- 실행한 테스트와 결과
- 화면 변경이 있는 경우 변경 전·후 스크린샷
- 리뷰어가 확인해야 할 사항

PR 제목도 커밋 규칙과 동일하게 작성한다.

```text
feat: 로그인 기능 추가
```

### 4.4 리뷰 및 `develop` 병합

- 리뷰어의 승인 없이 PR을 병합하지 않는다.
- CI, 테스트, 빌드가 모두 통과한 뒤 병합한다.
- 리뷰 의견을 반영한 뒤 다시 리뷰를 요청한다.
- 충돌이 발생한 경우 작업자가 해결하고 테스트한 뒤 push한다.
- `feature/`, `bugfix/`, `docs/`, `refactor/`, `test/`, `chore/` 브랜치는 PR을 통해 `develop`에 병합한다.
- GitHub에서는 `Create a merge commit` 방식을 기본으로 사용한다.
- `Rebase and merge`, `Squash and merge`, `main` 또는 `develop`으로의 직접 push는 사용하지 않는다.

### 4.5 릴리스 브랜치 생성 및 배포

`develop`에 다음 릴리스의 기능이 모두 통합되고 출시 범위가 확정되면 `release` 브랜치를 생성한다. 릴리스 브랜치에서는 최종 테스트, 버그 수정, 문서 및 버전 변경만 수행한다.

```bash
git fetch origin
git switch develop
git pull --no-rebase origin develop
git switch -c release/v1.0.0
git push -u origin release/v1.0.0
```

안정화가 끝나면 동일한 `release` 브랜치로 다음 두 개의 PR을 생성한다.

1. `release/v1.0.0` → `main`: 운영 배포용 변경사항 반영
2. `release/v1.0.0` → `develop`: 릴리스 중 발생한 수정사항을 다음 개발 기준에 반영

두 PR 모두 리뷰와 CI 검증을 통과한 뒤 merge commit 방식으로 병합한다. `main` 병합 후에는 버전 태그를 생성하고 원격 저장소에 push한다.

```bash
git switch main
git pull --no-rebase origin main
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0
```

릴리스 브랜치가 열려 있는 동안에는 새로운 기능을 추가하지 않는다. 새로운 기능이 필요하면 `develop`에서 별도의 작업 브랜치를 생성하여 다음 릴리스로 넘긴다.

### 4.6 긴급 수정 브랜치 생성 및 배포

운영 중인 `main`에서 긴급한 오류가 발견되면 `hotfix` 브랜치를 생성한다.

```bash
git fetch origin
git switch main
git pull --no-rebase origin main
git switch -c hotfix/31-payment-error
git push -u origin hotfix/31-payment-error
```

수정과 검증이 끝나면 동일한 `hotfix` 브랜치로 다음 두 개의 PR을 생성한다.

1. `hotfix/31-payment-error` → `main`: 운영 환경에 긴급 수정 반영
2. `hotfix/31-payment-error` → `develop`: 다음 릴리스에도 동일한 수정 반영

`main`에 병합한 뒤에는 패치 버전 태그를 생성한다. 진행 중인 `release` 브랜치가 있다면 해당 수정사항의 반영 여부도 확인하여 릴리스 버전에 누락되지 않도록 한다.

```bash
git switch main
git pull --no-rebase origin main
git tag -a v1.0.1 -m "Release v1.0.1"
git push origin v1.0.1
```

### 4.7 병합 후 정리

기능·일반 수정 브랜치는 `develop` 병합 후 삭제한다. `release`와 `hotfix` 브랜치는 `main`과 `develop` 양쪽의 PR이 모두 병합되고 태그가 생성된 뒤 삭제한다.

```bash
git switch develop
git pull --no-rebase origin develop
git branch -d feature/12-login
git push origin --delete feature/12-login
```

GitHub의 자동 브랜치 삭제가 켜져 있다면 원격 브랜치 삭제 명령은 생략할 수 있다.

## 5. 최신 기준 브랜치 반영 및 충돌 해결

작업 브랜치에 최신 기준 브랜치를 반영할 때는 rebase하지 않고 merge한다.

### 5.1 일반 작업 브랜치에 최신 `develop` 반영

```bash
git switch feature/12-login
git fetch origin
git merge origin/develop
```

### 5.2 `release` 브랜치에 변경사항 반영

릴리스 안정화 중 필요한 수정은 `release` 브랜치에서 직접 작업하고, `develop`에 있는 변경사항을 임의로 추가하지 않는다. 별도의 수정이 필요하면 릴리스 범위에 맞는 커밋을 `release` 브랜치에 반영한다.

### 5.3 `hotfix` 브랜치에 최신 `main` 반영

```bash
git switch hotfix/31-payment-error
git fetch origin
git merge origin/main
```

충돌이 발생하면 충돌 파일을 직접 수정한 뒤 다음 순서로 처리한다.

```bash
git add <충돌을-해결한-파일>
git commit -m "merge: 기준 브랜치 충돌 해결"
git push origin <현재-브랜치>
```

- 공유 브랜치에서 `git rebase`를 사용하지 않는다.
- `git push --force` 또는 `git push --force-with-lease`를 사용하지 않는다.
- PR 병합 전에는 해당 브랜치가 최신 기준 브랜치를 반영했고 테스트가 통과했는지 확인한다.
- `release`와 `hotfix`의 수정사항이 반대편 장기 브랜치에 누락되지 않았는지 확인한다.

## 6. 브랜치 보호 설정

GitHub 저장소의 `main`과 `develop` 브랜치에는 다음 보호 규칙을 적용한다.

### 6.1 `main` 브랜치

- PR을 통해서만 변경사항 반영
- 최소 1명 이상의 리뷰 승인 필수
- 필수 CI, 테스트 및 빌드 통과 필수
- 병합 전 최신 `main`과의 충돌 해결 필수
- force push 금지
- `main` 브랜치 삭제 금지
- merge commit만 허용하고 `Rebase and merge`, `Squash and merge` 비활성화
- 운영 배포 버전에 대한 태그 생성 및 보호

### 6.2 `develop` 브랜치

- PR을 통해서만 변경사항 반영
- 최소 1명 이상의 리뷰 승인 필수
- 필수 CI, 테스트 및 빌드 통과 필수
- 병합 전 최신 `develop`과의 충돌 해결 필수
- force push 금지
- `develop` 브랜치 삭제 금지
- merge commit만 허용하고 `Rebase and merge`, `Squash and merge` 비활성화

`release/*`와 `hotfix/*` 브랜치에도 필요에 따라 PR, 리뷰 승인, CI 통과 및 force push 금지 규칙을 적용한다. `release`와 `hotfix` PR은 각각 `main`과 `develop` 양쪽을 대상으로 생성해야 한다.

## 7. PR 병합 전 체크리스트

- [ ] `main` 또는 `develop`에 직접 커밋하거나 push하지 않았는가?
- [ ] 브랜치 이름에 올바른 접두사와 형식을 사용했는가?
- [ ] 브랜치 생성 기준이 올바른가? (`feature` 등은 `develop`, `hotfix`는 `main`)
- [ ] PR의 base 브랜치가 작업 유형에 맞는가?
  - [ ] 일반 작업: `develop`
  - [ ] `release/*`: `main` 및 `develop`
  - [ ] `hotfix/*`: `main` 및 `develop`
- [ ] 커밋과 PR 제목에 올바른 접두사를 사용했는가?
- [ ] 관련 이슈를 연결했는가?
- [ ] 테스트와 빌드를 실행했는가?
- [ ] 리뷰어의 승인을 받았는가?
- [ ] 최신 기준 브랜치와 충돌이 없는가?
- [ ] merge commit 방식으로 병합하도록 설정했는가?
- [ ] `release` 브랜치에 새로운 기능을 포함하지 않았는가?
- [ ] `release` 또는 `hotfix`의 수정사항을 양쪽 장기 브랜치에 모두 반영했는가?
- [ ] `main` 병합 후 버전 태그를 생성했는가?
- [ ] 문서, 테스트, 환경 설정 등 관련 파일을 함께 갱신했는가?
