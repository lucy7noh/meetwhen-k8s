# meetwhen-k8s — 쿠버네티스 배포 · 모니터링 · 오토스케일 프로젝트

> 친구들끼리 가능한 시간을 모아 약속을 정하는 웹앱(when2meet 스타일)을 **FastAPI**로 만들고,
> **쿠버네티스에 배포 → 모니터링(Prometheus/Grafana) → 오토스케일(HPA)** 까지 직접 구축한 인프라 포트폴리오 프로젝트입니다.

> ⭐ 이 프로젝트의 초점은 앱 기능이 아니라 **인프라(컨테이너 · 쿠버네티스 · 관측성 · 오토스케일)** 입니다. 앱은 그것을 실증하기 위한 무대입니다.

---

## 🎯 프로젝트 목표

시스템/인프라 엔지니어로서 아래를 **직접 구현하고 원리를 이해**하는 것을 목표로 했습니다.

- 컨테이너화된 애플리케이션을 쿠버네티스에 배포
- 상태 있는(stateful) 워크로드(PostgreSQL) + 영속 볼륨(PVC) 운영
- probe 기반 **자동복구(self-healing)**
- Prometheus/Grafana 기반 **관측성(observability)**
- 부하 기반 **오토스케일(HPA)** 구현 및 검증

## 🏗 아키텍처

```
[사용자] ─ kubectl port-forward ─▶ [meetwhen Service]
                                        │
                                        ▼
                                 [meetwhen Pod × N]  ◀── HPA (2~5개, CPU 50% 기준)
                                        │
                                        ▼
                                 [postgres Service] ─▶ [postgres Pod] ─▶ [PVC 영속 저장소]

관측성:  meetwhen /metrics ─(ServiceMonitor)─▶ [Prometheus] ─▶ [Grafana 대시보드]
오토스케일:  [metrics-server] ─(파드 CPU)─▶ [HPA] ─▶ 파드 수 자동 조절
```

*현재 로컬 쿠버네티스(Docker Desktop) 환경에 배포되어 있으며, 클라우드 배포는 향후 계획입니다(아래 참고).*

## 🧰 기술 스택

| 영역 | 사용 기술 |
|------|-----------|
| 언어 / 앱 | Python, FastAPI |
| 컨테이너 | Docker |
| 오케스트레이션 | Kubernetes, Helm |
| 데이터 | PostgreSQL (PVC로 영속화) |
| 모니터링 | Prometheus, Grafana, Alertmanager (kube-prometheus-stack) |
| 오토스케일 | HorizontalPodAutoscaler, metrics-server |
| 부하 테스트 | 인클러스터 부하 생성 (busybox) |
| CI/CD | GitHub Actions, GHCR *(구성 완료, 클라우드 배포 시 연결 예정)* |

## 📸 스크린샷

> `screenshots/` 폴더에 이미지를 넣고 아래 경로를 맞춰주세요.

| 화면 | 이미지 |
|------|--------|
| 앱 실행 (약속 그리드) | `screenshots/app-running.png` |
| Grafana 대시보드 | `screenshots/grafana-dashboard.png` |
| 부하 시 CPU 급증 (`kubectl top pods`) | `screenshots/load-cpu-spike.png` |
| **HPA 오토스케일 (2→5 파드)** | `screenshots/hpa-scaleup.png` |

## ✨ 주요 구현

- **멀티서비스 배포** — 앱(meetwhen)과 DB(PostgreSQL)를 각각 Deployment/Service로 분리 배포, ConfigMap·Secret으로 설정 주입, PVC로 DB 데이터 영속화.
- **자동복구(self-healing)** — liveness/readiness probe와 Deployment를 통해, DB 준비 전 앱이 죽어도 자동 재시작되어 복구되는 것을 확인.
- **관측성** — kube-prometheus-stack으로 Prometheus + Grafana를 배포하고, ServiceMonitor로 앱의 `/metrics`를 수집하여 서비스 지표를 대시보드로 확인.
- **오토스케일(HPA)** — metrics-server 기반으로 파드 CPU를 측정, 부하를 주면 CPU 사용률이 목표(50%)를 초과할 때 파드가 **2개 → 5개로 자동 확장**되고, 부하가 줄면 다시 축소되는 것을 검증.

## 🔥 트러블슈팅 & 배운 점

> 실제로 막히고 해결한 과정들입니다. (인프라 실무의 핵심은 여기에 있다고 생각합니다.)

| 문제 | 원인 | 해결 | 배운 점 |
|------|------|------|---------|
| 앱 파드가 `CrashLoopBackOff` 후 스스로 복구 | 앱이 Postgres보다 먼저 기동 → DB 접속 실패로 종료 | Deployment + probe가 자동 재시작 → Postgres 준비 후 정상 기동 (RESTARTS 2회) | 쿠버네티스의 자동복구 원리, probe의 역할 |
| HPA가 CPU를 `<unknown>`으로 표시 | metrics-server 미설치 | metrics-server 설치 | HPA는 metrics-server의 파드 지표에 의존한다는 것 |
| metrics-server가 기동 실패 | 로컬 클러스터의 kubelet 인증서를 검증하지 못함 | `--kubelet-insecure-tls` 플래그 추가 | 로컬/개발 클러스터의 TLS 검증 이슈 |
| node-exporter `CrashLoopBackOff` | 호스트 파일시스템 마운트가 Docker Desktop 환경과 비호환 | 단일 로컬 노드에서 불필요하여 비활성화 | 컴포넌트의 목적(노드 지표)과 환경 제약 이해 |
| 부하를 줘도 파드 CPU가 오르지 않음 | Git Bash(MSYS)가 kubectl 명령의 경로(`/bin/sh`, `/dev/null`, URL)를 Windows 경로로 자동 변환 → 컨테이너 명령이 깨짐 | `MSYS_NO_PATHCONV=1`로 경로 변환 비활성화 | 셸 환경이 명령 전달에 미치는 영향, 원인 격리 디버깅 |

## ⚡ 실행 방법 (로컬 재현)

**사전 준비:** Docker Desktop(Kubernetes 활성화), kubectl, Helm

```bash
# 1) 앱 이미지 빌드
docker build -t meetwhen:local .

# 2) 앱 + DB 배포
kubectl apply -f meetwhen-local.yaml

# 3) 접속
kubectl port-forward svc/meetwhen 8000:80
#   → http://localhost:8000

# 4) 모니터링 설치
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm install monitoring prometheus-community/kube-prometheus-stack --set nodeExporter.enabled=false
kubectl apply -f k8s/servicemonitor.yaml
kubectl port-forward svc/monitoring-grafana 3000:80
#   → http://localhost:3000  (admin / prom-operator)

# 5) 오토스케일
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
kubectl patch deployment metrics-server -n kube-system --type='json' \
  -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
kubectl apply -f k8s/hpa.yaml
kubectl get hpa meetwhen --watch
```

## 📊 모니터링 & 오토스케일 정책

- **수집 지표:** 앱의 요청 수·응답시간(`/metrics`), 클러스터/파드 리소스
- **오토스케일 정책(HPA):** CPU 평균 사용률 50% 초과 시 확장, 최소 2 / 최대 5 파드
- **검증:** 부하 생성 시 파드 CPU가 요청량(request) 대비 400% 이상까지 상승 → HPA가 5개까지 확장 → 부하 분산으로 사용률 수렴 확인

## 🚀 향후 계획

- **클라우드 배포** — 오라클 클라우드(k3s) 또는 AWS에 배포 + 실제 도메인 + Let's Encrypt HTTPS *(레포에 매니페스트 구성 완료: `k8s/ingress.yaml`, `k8s/cert-issuer.example.yaml`)*
- **CI/CD 연결** — GitHub Actions로 이미지 빌드·배포 자동화 *(워크플로 구성 완료: `.github/workflows/ci-cd.yaml`)*
- **GitOps** — ArgoCD 도입
- **알림** — Alertmanager → Discord/Slack 연동, SLI/SLO 정의

## 🙋 회고

수동으로 서버를 구축하던 경험을 넘어, **컨테이너 오케스트레이션 · 관측성 · 오토스케일**이라는 현대 인프라의 핵심 흐름을 직접 손으로 구현하며 이해했습니다. 특히 여러 환경 이슈(TLS 검증, 셸 경로 변환 등)를 원인 격리로 해결하는 과정에서, "동작하게 만드는 것"과 "왜 그렇게 되는지 이해하는 것"의 차이를 배웠습니다.

---

*개인 학습 · 포트폴리오 프로젝트*
