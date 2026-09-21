FROM alpine:edge

RUN apk add --no-cache \
      ca-certificates \
      github-cli \
      jq \
      python3 \
    && addgroup -S dashboard \
    && adduser -S -G dashboard -u 10001 dashboard \
    && mkdir -p /workspace/reports /usr/local/share/security-dashboard \
    && chown -R dashboard:dashboard /workspace /usr/local/share/security-dashboard

COPY --chmod=0555 scripts/security_report.sh /usr/local/bin/security-report
COPY --chmod=0444 scripts/report_api.py /usr/local/lib/report_api.py
COPY --chown=dashboard:dashboard dashboard/ /usr/local/share/security-dashboard/

USER 10001:10001
WORKDIR /workspace

ENV HOME=/tmp
EXPOSE 8080

CMD ["python3", "/usr/local/lib/report_api.py"]
