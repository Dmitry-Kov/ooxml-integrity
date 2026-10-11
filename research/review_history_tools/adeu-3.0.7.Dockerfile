# adeu 3.0.7 (tag v3.0.7, commit 096baa88b8ea6980ad305abaae8e31b49c3c3918) for the
# review-history recheck (evidence/review-history-recheck). Built exactly as the
# frozen benchmark's adeu.Dockerfile, with the new release. The network is used
# only while building; every attempt runs in its own container with --network none.
# Build context: the tag's python/ directory as adeu-src/ (git archive).
FROM python@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f

RUN pip install --no-cache-dir uv==0.12.20

COPY adeu-src /src
WORKDIR /src
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
RUN echo "9d5a0427912fc25f0eb2cd54e9f228a76ad526f306c188a427aec4957e8cbfef  uv.lock" | sha256sum -c - \
 && uv sync --frozen --no-dev --python /usr/local/bin/python3.12
RUN .venv/bin/python -c "import importlib.metadata as m; assert m.version('adeu') == '3.0.7'" \
 && uv pip freeze --python .venv/bin/python > /src/freeze.txt
