# ROGUE simulated/hardware SDR Agent image.
#
# M0 scope: run the minimal presence-heartbeat agent defined in
# agents/common/main.py. Vendor-specific adapters (Ettus, Deepwave) are
# added once the simulated agent and Replay Plan contract are stable
# (see docs/architecture/implementation-plan.md, M9/M10).

FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY backend/rogue ./backend/rogue
COPY agents ./agents

RUN pip install --no-cache-dir .

ENV PYTHONPATH=/app

CMD ["python", "-m", "agents.common.main"]
