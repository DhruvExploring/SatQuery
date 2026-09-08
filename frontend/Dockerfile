# syntax=docker/dockerfile:1

FROM node:20-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
# Copy only the exact source paths needed to build — never the whole
# frontend/ directory. A host-side frontend/node_modules or frontend/dist
# (common after running `npm install`/`npm run dev` locally) must never reach
# this stage; it would shadow the fresh, container-native node_modules that
# npm ci just installed above and can leave `vite` (and other bin symlinks)
# broken for this platform.
COPY frontend/index.html frontend/vite.config.js ./
COPY frontend/src/ src/
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY frontend/docker-entrypoint.sh /docker-entrypoint.d/40-env-config.sh
RUN chmod +x /docker-entrypoint.d/40-env-config.sh

EXPOSE 80
