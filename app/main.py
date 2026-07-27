"""
meetwhen — 친구들끼리 가능한 시간을 모아 약속을 정하는 앱 (when2meet 스타일)

이 앱은 '무대'입니다. 주인공은 쿠버네티스 · 모니터링 · 오토스케일이에요.
그래서 코드는 최대한 단순하게, 대신 인프라가 써먹을 고리(health/metrics/CPU부하)를
전부 넣어뒀습니다.

- GET  /                         : 이벤트 생성 폼
- POST /events                   : 이벤트 생성 → 공유 링크로 리다이렉트
- GET  /events/{event_id}        : 캘린더 그리드 + 현재 집계
- POST /events/{event_id}/availability : 참여자 가능시간 제출
- GET  /events/{event_id}/result : 가장 많이 겹치는 시간(JSON)
- GET  /events/{event_id}/heatmap.png  : 겹침 히트맵 이미지  ← CPU 부하 지점(HPA 데모)
- GET  /health                   : liveness/readiness probe 용
- GET  /metrics                  : Prometheus 수집 (instrumentator가 자동 등록)
"""
import io
import os
import secrets
from datetime import datetime, timezone

from fastapi import FastAPI, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from prometheus_fastapi_instrumentator import Instrumentator
from PIL import Image, ImageDraw
from sqlalchemy import create_engine, Column, String, Integer, DateTime, JSON, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# ---------------------------------------------------------------------------
# 설정 (환경변수) — 로컬은 SQLite, 컨테이너/쿠버네티스에선 DATABASE_URL로 Postgres 주입
# ---------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
APP_TITLE = os.getenv("APP_TITLE", "meetwhen")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


# ---------------------------------------------------------------------------
# 데이터 모델
# ---------------------------------------------------------------------------
class Event(Base):
    __tablename__ = "events"
    id = Column(String, primary_key=True)          # 공유 링크에 쓰이는 짧은 코드
    title = Column(String, nullable=False)
    dates = Column(JSON, nullable=False)            # ["2026-08-01", "2026-08-02", ...]
    times = Column(JSON, nullable=False)            # ["10:00", "11:00", ...]
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    participants = relationship("Participant", back_populates="event", cascade="all, delete-orphan")


class Participant(Base):
    __tablename__ = "participants"
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String, ForeignKey("events.id"), nullable=False)
    name = Column(String, nullable=False)
    slots = Column(JSON, nullable=False, default=list)   # ["2026-08-01|10:00", ...]
    event = relationship("Event", back_populates="participants")


Base.metadata.create_all(bind=engine)


# ---------------------------------------------------------------------------
# 앱 + 모니터링(/metrics 자동 노출)
# ---------------------------------------------------------------------------
app = FastAPI(title=APP_TITLE)
templates = Jinja2Templates(directory="templates")
Instrumentator().instrument(app).expose(app)   # → GET /metrics


def slot_key(date: str, time: str) -> str:
    return f"{date}|{time}"


def aggregate(event: Event) -> dict:
    """slot -> 가능한 사람 수 집계."""
    counts: dict[str, int] = {}
    for p in event.participants:
        for s in (p.slots or []):
            counts[s] = counts.get(s, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# 라우트
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "index.html", {"app_title": APP_TITLE})


@app.post("/events")
def create_event(
    title: str = Form(...),
    dates: str = Form(...),        # 쉼표 또는 줄바꿈으로 구분된 날짜들
    start_hour: int = Form(9),
    end_hour: int = Form(18),
):
    date_list = [d.strip() for d in dates.replace("\n", ",").split(",") if d.strip()]
    if not date_list:
        raise HTTPException(status_code=400, detail="날짜를 최소 1개 입력하세요.")
    start_hour = max(0, min(23, start_hour))
    end_hour = max(start_hour + 1, min(24, end_hour))
    time_list = [f"{h:02d}:00" for h in range(start_hour, end_hour)]

    event_id = secrets.token_urlsafe(6)
    db = SessionLocal()
    try:
        db.add(Event(id=event_id, title=title.strip(), dates=date_list, times=time_list))
        db.commit()
    finally:
        db.close()
    return RedirectResponse(url=f"/events/{event_id}", status_code=303)


@app.get("/events/{event_id}", response_class=HTMLResponse)
def view_event(request: Request, event_id: str):
    db = SessionLocal()
    try:
        event = db.get(Event, event_id)
        if not event:
            raise HTTPException(status_code=404, detail="이벤트를 찾을 수 없습니다.")
        counts = aggregate(event)
        best = max(counts.values()) if counts else 0
        return templates.TemplateResponse(
            request,
            "event.html",
            {
                "app_title": APP_TITLE,
                "event": event,
                "counts": counts,
                "best": best,
                "total": len(event.participants),
                "slot_key": slot_key,
            },
        )
    finally:
        db.close()


@app.post("/events/{event_id}/availability")
async def submit_availability(event_id: str, request: Request):
    # 폼에서 name + 체크된 slot들(name="slot", 여러 개)을 async로 파싱
    form = await request.form()
    name = (form.get("name") or "익명").strip()
    slots = form.getlist("slot")
    db = SessionLocal()
    try:
        event = db.get(Event, event_id)
        if not event:
            raise HTTPException(status_code=404, detail="이벤트를 찾을 수 없습니다.")
        db.add(Participant(event_id=event_id, name=name, slots=slots))
        db.commit()
    finally:
        db.close()
    return RedirectResponse(url=f"/events/{event_id}", status_code=303)


@app.get("/events/{event_id}/result")
def result(event_id: str):
    db = SessionLocal()
    try:
        event = db.get(Event, event_id)
        if not event:
            raise HTTPException(status_code=404, detail="이벤트를 찾을 수 없습니다.")
        counts = aggregate(event)
        if not counts:
            return JSONResponse({"event": event.title, "best_slots": [], "message": "아직 제출한 사람이 없어요."})
        best = max(counts.values())
        best_slots = sorted([s for s, c in counts.items() if c == best])
        return JSONResponse({
            "event": event.title,
            "participants": len(event.participants),
            "best_count": best,
            "best_slots": best_slots,
        })
    finally:
        db.close()


@app.get("/events/{event_id}/heatmap.png")
def heatmap(event_id: str):
    """
    가능 인원 히트맵을 PNG로 렌더링.
    ⚠️ 의도적으로 서버에서 이미지를 그리는 CPU 작업 → k6로 부하를 주면
       CPU가 올라가 HPA(오토스케일)가 동작하는 걸 시연할 수 있음.
    """
    db = SessionLocal()
    try:
        event = db.get(Event, event_id)
        if not event:
            raise HTTPException(status_code=404, detail="이벤트를 찾을 수 없습니다.")
        counts = aggregate(event)
        dates, times = event.dates, event.times
        maxc = max(counts.values()) if counts else 0

        cell_w, cell_h = 90, 34
        pad_l, pad_t = 70, 40
        w = pad_l + cell_w * len(dates) + 20
        h = pad_t + cell_h * len(times) + 20
        img = Image.new("RGB", (w, h), "white")
        d = ImageDraw.Draw(img)

        # 헤더(날짜)
        for ci, date in enumerate(dates):
            d.text((pad_l + ci * cell_w + 6, 12), date[5:], fill="black")  # MM-DD
        # 행(시간) + 셀
        for ri, t in enumerate(times):
            d.text((10, pad_t + ri * cell_h + 8), t, fill="black")
            for ci, date in enumerate(dates):
                c = counts.get(slot_key(date, t), 0)
                ratio = (c / maxc) if maxc else 0
                # 흰색 → 초록으로 진해짐
                r = int(255 - 175 * ratio)
                g = int(255 - 60 * ratio)
                b = int(255 - 190 * ratio)
                x0 = pad_l + ci * cell_w
                y0 = pad_t + ri * cell_h
                d.rectangle([x0, y0, x0 + cell_w - 2, y0 + cell_h - 2], fill=(r, g, b), outline=(220, 220, 220))
                if c:
                    d.text((x0 + cell_w // 2 - 3, y0 + 8), str(c), fill=(20, 60, 30))

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return Response(content=buf.getvalue(), media_type="image/png")
    finally:
        db.close()


@app.get("/health")
def health():
    """probe 용. DB 접속까지 확인하면 readiness로도 좋음."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
