# ROGUE control-plane API image.
#
# M0 scope: install the rogue package and run the FastAPI health-check
# shell. Kept single-stage until a concrete need (native build deps,
# image-size pressure) justifies a multi-stage build.

FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY backend/rogue ./backend/rogue

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "rogue.main:app", "--host", "0.0.0.0", "--port", "8000"]
