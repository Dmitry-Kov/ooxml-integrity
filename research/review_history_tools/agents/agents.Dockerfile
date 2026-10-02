# Coding agents for wave 2 of the review-history benchmark, one target each.
# Every agent gets the same environment: Python 3.12 with python-docx 1.2.0
# and lxml from a hashed lock, and nothing else to install from. The agent CLIs
# are the native linux-arm64 builds their npm packages install, taken from the
# published tarballs and checked by SHA-256 (npm's sha512 integrity was checked
# when they were fetched). The network is used only while building.
# Build context: python.lock and the three tarballs (see amendment 008).
FROM python@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f AS base

COPY python.lock /python.lock
RUN pip install --no-cache-dir --root-user-action=ignore --require-hashes --no-deps -r /python.lock \
 && pip freeze > /freeze.txt \
 && mkdir -p /work && chmod 1777 /work
WORKDIR /work

FROM base AS claude
COPY claude-code-linux-arm64-2.1.287.tgz /tmp/agent.tgz
RUN echo "33ae16d93e1e82b9de10684b540650a9ffbb654eb317e4bfc1ff0f932816f1bc  /tmp/agent.tgz" | sha256sum -c - \
 && mkdir -p /opt/claude-code && tar -xzf /tmp/agent.tgz -C /opt/claude-code && rm /tmp/agent.tgz \
 && chmod -R a+rX /opt/claude-code && ln -s /opt/claude-code/package/claude /usr/local/bin/claude \
 && HOME=/tmp claude --version

FROM base AS codex
COPY codex-0.160.0-linux-arm64.tgz /tmp/agent.tgz
RUN echo "9286a7e01d500ab224c9e5b4b223b7adf5dd901fba23efd6a438316426798b17  /tmp/agent.tgz" | sha256sum -c - \
 && mkdir -p /opt/codex && tar -xzf /tmp/agent.tgz -C /opt/codex && rm /tmp/agent.tgz \
 && chmod -R a+rX /opt/codex \
 && ln -s /opt/codex/package/vendor/aarch64-unknown-linux-musl/bin/codex /usr/local/bin/codex \
 && HOME=/tmp codex --version
# The npm launcher puts the bundled ripgrep on PATH; do the same.
ENV PATH=/opt/codex/package/vendor/aarch64-unknown-linux-musl/codex-path:$PATH

FROM base AS opencode
COPY opencode-linux-arm64-1.18.34.tgz /tmp/agent.tgz
RUN echo "6f212b830b26bf72012f1665559ddb5fd7e928294971d3d1c99a0f9097a3d311  /tmp/agent.tgz" | sha256sum -c - \
 && mkdir -p /opt/opencode && tar -xzf /tmp/agent.tgz -C /opt/opencode && rm /tmp/agent.tgz \
 && chmod -R a+rX /opt/opencode && ln -s /opt/opencode/package/bin/opencode /usr/local/bin/opencode \
 && HOME=/tmp opencode --version
