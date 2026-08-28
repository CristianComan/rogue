# ROGUE Scenario Editor UI image.
#
# M3 scope: dev-server target only, matching how this milestone is actually
# run and verified (see docs/architecture/implementation-plan.md). A
# production static-build stage is a later-milestone concern once there's a
# deployment story for it.

FROM node:20-slim

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN npm ci

COPY frontend ./

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
