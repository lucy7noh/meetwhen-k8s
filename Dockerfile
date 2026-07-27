# build context = 레포 루트 (docker build -t meetwhen .)
FROM python:3.11-slim

WORKDIR /app

# 의존성 먼저 복사 → 레이어 캐시 활용
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 앱 코드 복사 (main.py, templates/)
COPY app/ .

EXPOSE 8000

# 컨테이너에선 SQLite 대신 DATABASE_URL(Postgres)을 주입해서 쓴다
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
