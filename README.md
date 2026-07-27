# meetwhen — 쿠버네티스 클라우드 배포 & 모니터링 프로젝트

친구들끼리 가능한 시간을 모아 약속을 정하는 웹앱(when2meet 스타일)을,
**FastAPI로 만들어 클라우드 쿠버네티스(k3s)에 배포**하고,
HTTPS · 모니터링 · 자동복구 · 오토스케일까지 구성한 인프라 포트폴리오 프로젝트.

> ⭐ 이 프로젝트의 주인공은 앱이 아니라 **인프라(Kubernetes · 모니터링 · 오토스케일)** 입니다.
> 앱은 그걸 보여주기 위한 무대예요.

---

## 🔗 라이브 (배포 후 채우기)
- 서비스: `https://YOUR_DOMAIN`
- Grafana 대시보드: (스크린샷 첨부)

## 🏗 아키텍처

```
사용자 ──▶ 도메인(sslip.io/DuckDNS) ──▶ 클라우드 VM (k3s 클러스터)
                                          │
                                          ├─ Ingress(Traefik) + cert-manager(HTTPS)
                                          ├─ meetwhen App Pod ×N (FastAPI)   ← HPA로 오토스케일
                                          ├─ Postgres Pod + PVC (영속 저장)
                                          └─ kube-prometheus-stack (Prometheus·Grafana·Alertmanager)
```

## 🧰 기술 스택
| 영역 | 사용 기술 |
|------|-----------|
| 언어/앱 | Python, FastAPI |
| 컨테이너 | Docker |
| 오케스트레이션 | Kubernetes (k3s), Helm |
| 네트워킹 | Ingress(Traefik), cert-manager, Let's Encrypt |
| 데이터 | PostgreSQL (PVC) |
| 모니터링 | Prometheus, Grafana, Alertmanager |
| 운영 | HPA(오토스케일), liveness/readiness probe |
| 부하테스트 | k6 |
| CI/CD | GitHub Actions, GHCR |
| 클라우드 | Oracle Cloud (Always Free) |

## 📁 레포 구조
```
meetwhen/
├── app/                  # FastAPI 앱 (main.py, templates/, requirements.txt)
├── Dockerfile
├── docker-compose.yml    # 로컬 개발용 (app + postgres)
├── k8s/                  # 쿠버네티스 매니페스트
│   ├── configmap.yaml
│   ├── secret.example.yaml
│   ├── postgres.yaml
│   ├── app-deployment.yaml
│   ├── app-service.yaml
│   ├── ingress.yaml
│   ├── hpa.yaml
│   ├── servicemonitor.yaml
│   └── cert-issuer.example.yaml
├── loadtest/script.js    # k6 부하테스트 (HPA 시연)
└── .github/workflows/ci-cd.yaml
```

---

## ⚡ 1. 로컬에서 먼저 실행

가장 빠른 방법 (SQLite, 의존성만 설치):
```bash
cd app
pip install -r requirements.txt
python main.py            # http://localhost:8000
```

Docker Compose (앱 + Postgres, 실제 배포와 비슷한 구성):
```bash
docker compose up --build   # http://localhost:8000
```

## 🐳 2. 이미지 빌드 & 푸시
로컬에서 직접:
```bash
docker build -t ghcr.io/OWNER/meetwhen:latest .
docker push ghcr.io/OWNER/meetwhen:latest
```
또는 그냥 `main`에 push → **GitHub Actions가 자동으로 빌드·푸시** (`.github/workflows/ci-cd.yaml`).
> `OWNER`는 소문자 GitHub 계정명. GHCR 이미지는 소문자만 허용됩니다.

## ☁️ 3. 클라우드 + k3s 준비
1. **오라클 클라우드 Always Free** VM(Ubuntu) 생성 → SSH 접속, 방화벽 80/443 오픈
2. k3s 설치:
   ```bash
   curl -sfL https://get.k3s.io | sh -
   sudo k3s kubectl get nodes        # Ready 확인
   ```
3. 로컬에서 쓰려면 `/etc/rancher/k3s/k3s.yaml`(kubeconfig)을 복사해 server 주소를 VM 공인 IP로 수정
4. **도메인 연결**: `sslip.io`를 쓰면 도메인 구매 없이 `meetwhen.<VM-IP>.sslip.io` 형태로 바로 사용 가능

## 🔒 4. cert-manager (HTTPS)
```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/latest/download/cert-manager.yaml
cp k8s/cert-issuer.example.yaml k8s/cert-issuer.yaml   # 이메일 수정
kubectl apply -f k8s/cert-issuer.yaml
```

## 🚀 5. 앱 배포
```bash
# 1) 시크릿 준비 (비밀번호 넣기)
cp k8s/secret.example.yaml k8s/secret.yaml   # 값 수정! (git에 안 올라감)
kubectl apply -f k8s/secret.yaml

# 2) 나머지 전부 적용
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/app-deployment.yaml     # image의 OWNER 먼저 수정!
kubectl apply -f k8s/app-service.yaml
kubectl apply -f k8s/ingress.yaml            # YOUR_DOMAIN 먼저 수정!
kubectl apply -f k8s/hpa.yaml

# 3) 확인
kubectl get pods,svc,ingress,hpa
# → https://YOUR_DOMAIN 접속!
```

## 📊 6. 모니터링 (Prometheus + Grafana)
```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm install monitoring prometheus-community/kube-prometheus-stack
kubectl apply -f k8s/servicemonitor.yaml     # 앱 /metrics 수집 연결

# Grafana 접속 (포트포워딩)
kubectl port-forward svc/monitoring-grafana 3000:80
# 초기 비번: kubectl get secret monitoring-grafana -o jsonpath="{.data.admin-password}" | base64 -d
```

## 🔥 7. 오토스케일(HPA) 시연
```bash
# 이벤트 하나 만들고 EVENT_ID 확인 후:
k6 run -e BASE_URL=https://YOUR_DOMAIN -e EVENT_ID=xxxx loadtest/script.js
# 다른 창에서 관찰:
watch kubectl get hpa,pods     # CPU 오르면 파드가 2→5개로 늘어남!
```

---

## ⚠️ 보안 (중요)
- **비밀번호·인증서·kubeconfig는 절대 커밋 금지.** `secret.yaml`, `cert-issuer.yaml`, `kubeconfig`는 이미 `.gitignore` 처리됨.
- 실수로 시크릿을 커밋했다면 **즉시 값을 재발급/변경**하세요 (git 히스토리에 남습니다).
- 공개 레포로 전환하기 전에 `git log -p | grep -i password` 등으로 한 번 훑어보기.

## 🐛 트러블슈팅 (겪은 문제를 여기 기록 — 면접 핵심 소재!)
| 문제 | 원인 | 해결 |
|------|------|------|
| 예: Pod가 CrashLoopBackOff | DB 접속 실패(Secret 오타) | DATABASE_URL 비번 일치 확인 |
| 예: HTTPS 인증서 안 나옴 | DNS 전파 전 / 80 포트 막힘 | A레코드·방화벽 확인, `kubectl describe certificate` |
| ... | ... | ... |

## 🚀 배운 점 / 다음 계획
- (회고 작성)
- 개선 방향: 멀티노드 클러스터, GitOps(ArgoCD), 로그 수집(Loki), 알림 고도화 등

---
*이 프로젝트는 방학 4~6주 인프라 포트폴리오 로드맵의 실습 결과물입니다.*
