# Stage 1: Prepare static frontend assets
FROM alpine:3.20 AS builder

WORKDIR /build
COPY index.html nginx.conf ./

# Stage 2: Unprivileged Nginx runtime image
FROM nginx:1.27-alpine AS runtime

RUN addgroup -S appuser && \
    adduser -S -G appuser appuser && \
    sed -i 's,/run/nginx.pid,/tmp/nginx.pid,' /etc/nginx/nginx.conf && \
    chown -R appuser:appuser /var/cache/nginx /var/log/nginx /etc/nginx/conf.d /usr/share/nginx/html

COPY --from=builder --chown=appuser:appuser /build/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder --chown=appuser:appuser /build/index.html /usr/share/nginx/html/index.html

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/"]

CMD ["nginx", "-g", "daemon off;"]
