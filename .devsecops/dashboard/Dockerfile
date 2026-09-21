FROM alpine:3.22

# El contenedor solo incluye las herramientas necesarias para descargar y mostrar informes.
RUN apk add --no-cache \
      ca-certificates \
      github-cli \
      jq \
      python3 \
    && addgroup -S dashboard \
    && adduser -S -G dashboard -u 10001 dashboard \
    && mkdir -p /workspace/reports /usr/local/share/security-dashboard \
    && chown -R dashboard:dashboard /workspace /usr/local/share/security-dashboard

COPY --chmod=0555 security_report.sh /usr/local/bin/security-report
COPY --chmod=0444 report_api.py /usr/local/lib/report_api.py
COPY --chown=dashboard:dashboard static/ /usr/local/share/security-dashboard/

# El panel se ejecuta sin permisos de administrador.
USER 10001:10001
WORKDIR /workspace

ENV HOME=/tmp
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q -O - http://127.0.0.1:8080/health >/dev/null || exit 1

CMD ["python3", "/usr/local/lib/report_api.py"]
