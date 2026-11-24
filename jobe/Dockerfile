# Rebuild on top of JobeInABox so Ubuntu PHP/security updates are applied at
# image build time. Override the base with JOBE_BASE (tag or digest) if needed.
ARG JOBE_BASE=trampgeek/jobeinabox:latest
FROM ${JOBE_BASE}

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
