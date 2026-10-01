# adeu 3.0.6 (tag v3.0.6, commit df9e00ccae1421baa9591ffd4a2cdceae9cdcd4a) for the
# review-history benchmark. The network is used only while building; every
# attempt runs in its own container with --network none (see the adapter).
# Build context: the tag's python/ directory as adeu-src/ (git archive).
FROM python@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f

RUN pip install --no-cache-dir uv==0.12.20

COPY adeu-src /src
WORKDIR /src
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
RUN uv sync --frozen --no-dev --python /usr/local/bin/python3.12
RUN .venv/bin/python -c "import importlib.metadata as m; assert m.version('adeu') == '3.0.6'" \
 && uv pip freeze --python .venv/bin/python > /src/freeze.txt
