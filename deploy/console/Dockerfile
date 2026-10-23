# Console image almi-license-console (E07-01): static build served by Nginx.
#   docker build -f deploy/console/Dockerfile -t almi-license-console .
# API_UPSTREAM is the Django server the console talks to (same origin, cookies and CSRF).
FROM node:22 AS build
WORKDIR /app
COPY console/package.json console/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY console/ ./
RUN npm run build

FROM nginx:1.27
ENV API_UPSTREAM=http://api:8000 \
    NGINX_RESOLVER=127.0.0.11
# Only these variables are substituted: $uri, $host and the like stay nginx variables.
ENV NGINX_ENVSUBST_FILTER=^(API_UPSTREAM|NGINX_RESOLVER)$
COPY deploy/console/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
