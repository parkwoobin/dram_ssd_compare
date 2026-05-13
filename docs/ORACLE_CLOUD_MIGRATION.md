# Fly.io에서 Oracle Cloud Always Free로 이전하기

이 문서는 현재 FastAPI + SQLite + Docker Compose 구성을 Oracle Cloud Infrastructure(OCI) Always Free Compute VM으로 옮기는 절차입니다.

## 권장 구성

- VM: `VM.Standard.A1.Flex` 1 OCPU / 1~2 GB RAM 이상
- OS: Ubuntu 22.04/24.04 LTS 또는 Oracle Linux
- Runtime: Docker Engine + Docker Compose plugin
- App port: 컨테이너 내부 `8000`, VM 외부 `80`
- DB: SQLite 파일 `./data/prices.db`

OCI Always Free의 Ampere A1은 Arm 기반입니다. 현재 `python:3.12-slim` 이미지는 arm64를 지원하므로 별도 Dockerfile 분기는 필요 없습니다.

## 1. OCI VM 만들기

1. OCI Console에서 Compute Instance를 생성합니다.
2. Always Free eligible 표시가 있는 `VM.Standard.A1.Flex`를 선택합니다.
3. SSH 공개키를 등록합니다.
4. VCN/Subnet의 Ingress Security Rule에 아래 포트를 엽니다.

| Port | Source | Purpose |
|---:|---|---|
| 22 | 내 IP 권장 | SSH |
| 80 | `0.0.0.0/0` | HTTP |
| 443 | `0.0.0.0/0` | HTTPS를 나중에 붙일 경우 |

VM 안의 OS 방화벽도 80/443을 허용해야 합니다.

## 2. VM 초기 세팅

Ubuntu 예시:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
newgrp docker
docker version
docker compose version
```

Oracle Linux를 사용할 경우 Docker 설치 방식이 다를 수 있으니 Docker 공식 문서의 Linux 설치 절차를 따르세요.

## 3. 앱 배포

```bash
git clone https://github.com/parkwoobin/dram_ssd_compare.git
cd dram_ssd_compare
cp .env.example .env
mkdir -p data
```

Fly.io의 기존 SQLite 데이터를 유지하려면 Fly 볼륨에서 `prices.db`를 받아 `data/prices.db`에 둡니다. 데이터 이전 없이 새로 시작해도 된다면 빈 `data` 디렉터리만 있어도 앱 시작 시 초기 크롤링이 실행됩니다.

```bash
docker compose -f docker-compose.oracle.yml up -d --build
docker compose -f docker-compose.oracle.yml ps
curl http://127.0.0.1/health
curl http://127.0.0.1/health/ready
```

브라우저에서는 `http://<OCI_PUBLIC_IP>/`로 접속합니다.

## 4. Fly.io 데이터 가져오기

Fly 앱이 아직 살아 있고 볼륨에 `prices.db`가 있다면 아래 중 하나로 가져옵니다.

### 방법 A: fly ssh sftp 사용

로컬 PC에서:

```bash
fly ssh sftp get /app/data/prices.db ./prices.db -a dram-ssd-compare
```

그 다음 OCI VM으로 파일을 올립니다.

```bash
scp ./prices.db ubuntu@<OCI_PUBLIC_IP>:~/dram_ssd_compare/data/prices.db
```

VM 사용자명이 `ubuntu`가 아니면 이미지에 맞게 바꿉니다. Oracle Linux 이미지는 보통 `opc`를 사용합니다.

### 방법 B: Fly 셸에서 위치 확인

파일 경로가 다르면 셸로 확인합니다.

```bash
fly ssh console -a dram-ssd-compare
ls -lh /app/data
```

### 방법 C: 새로 크롤링 시작

이 서비스는 가격 스냅샷 앱이라 과거 추세 데이터가 꼭 필요하지 않다면 `data/prices.db` 이전 없이 시작해도 됩니다. `ENABLE_INITIAL_CRAWL=true`이면 DB가 비어 있을 때 첫 크롤링을 수행합니다.

## 5. 도메인과 HTTPS

Fly.io는 기본 HTTPS를 제공하지만, OCI VM 단독 배포는 직접 붙여야 합니다.

가장 간단한 운영 경로는 Caddy를 리버스 프록시로 붙이는 것입니다.

1. 도메인의 A 레코드를 OCI 공인 IP로 지정합니다.
2. OCI Security List 또는 Network Security Group에서 80/443 TCP를 엽니다.
3. `.env`에 도메인을 설정합니다.
4. HTTPS용 Compose 파일로 실행합니다.

```bash
sed -i 's/^DOMAIN=.*/DOMAIN=example.com/' .env
docker compose -f docker-compose.oracle.yml down
docker compose -f docker-compose.oracle-https.yml up -d --build
docker compose -f docker-compose.oracle-https.yml logs -f caddy
```

Caddy가 Let's Encrypt 인증서를 자동 발급합니다. DNS A 레코드가 OCI 공인 IP를 가리키고 80/443이 열려 있어야 인증서 발급이 성공합니다.

도메인이 없다면 우선 `http://<OCI_PUBLIC_IP>/`로 운영할 수 있습니다.

## 6. 운영 명령어

```bash
docker compose -f docker-compose.oracle.yml logs -f app
docker compose -f docker-compose.oracle.yml restart app
docker compose -f docker-compose.oracle.yml pull
docker compose -f docker-compose.oracle.yml up -d --build
docker stats dram-ssd-compare
```

DB 백업:

```bash
mkdir -p backups
cp data/prices.db "backups/prices-$(date +%Y%m%d-%H%M%S).db"
```

## 7. Fly.io 종료 전 체크리스트

- OCI에서 `/health`와 `/health/ready`가 정상 응답
- 메인 페이지와 `/api/compare/memory`, `/api/compare/ssd` 응답 확인
- `docker compose logs -f app`에서 스케줄러 시작 로그 확인
- 기존 도메인 DNS를 OCI 공인 IP로 전환
- DNS 전파 후 Fly 앱 중지

Fly 앱 중지:

```bash
fly scale count 0 -a dram-ssd-compare
```

완전히 삭제하기 전에는 며칠간 Fly 볼륨을 남겨 두는 것을 권장합니다.
