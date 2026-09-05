# ROGUE Scenario Editor UI image.
#
# M3 scope: dev-server target only, matching how this milestone is actually
# run and verified (see docs/architecture/implementation-plan.md). A
# production static-build stage is a later-milestone concern once there's a
# deployment story for it.
#
# Node version must track frontend/.nvmrc: a transitive maplibre-gl tooling
# dependency (@mapbox/jsonlint-lines-primitives) requires Node >=22, and
# .npmrc's engine-strict=true makes `npm ci` hard-fail rather than warn on
# that — this image fell behind .nvmrc once before and broke `docker compose
# up`'s ui build with exactly that error.

FROM node:24-slim

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN npm ci

COPY frontend ./

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
