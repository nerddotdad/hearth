# syntax=docker/dockerfile:1
# Triage sandbox image: kubectl, flux, shell utils + sandbox-agent (no LLM).

FROM debian:bookworm-slim

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      ca-certificates curl jq python3 \
      coreutils procps findutils grep sed gawk less \
      vim-tiny iproute2 iputils-ping dnsutils netcat-openbsd \
      util-linux tar gzip bash \
    && KVER="$(curl -fsSL https://dl.k8s.io/release/stable.txt)" \
    && curl -fsSL "https://dl.k8s.io/release/${KVER}/bin/linux/amd64/kubectl" -o /usr/local/bin/kubectl \
    && chmod +x /usr/local/bin/kubectl \
    && curl -fsSL https://github.com/fluxcd/flux2/releases/download/v2.7.2/flux_2.7.2_linux_amd64.tar.gz \
       | tar -xz -C /usr/local/bin flux \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY sandbox-agent.py /usr/local/bin/sandbox-agent
RUN chmod 755 /usr/local/bin/sandbox-agent

ENV SANDBOX_AGENT_PORT=8080
EXPOSE 8080
WORKDIR /workspace

CMD ["python3", "/usr/local/bin/sandbox-agent"]
