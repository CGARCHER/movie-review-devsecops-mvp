FROM alpine:edge

RUN apk add --no-cache \
      ca-certificates \
      github-cli \
      jq \
      python3 \
    && addgroup -S report \
    && adduser -S -G report -u 10001 report

COPY --chmod=0555 scripts/security_report.sh /usr/local/bin/security-report
COPY --chmod=0444 scripts/report_api.py /usr/local/lib/report_api.py

USER 10001:10001
WORKDIR /workspace

# GitHub CLI utiliza GH_TOKEN y no necesita guardar una sesion permanente.
ENV HOME=/tmp

ENTRYPOINT ["/usr/local/bin/security-report"]
