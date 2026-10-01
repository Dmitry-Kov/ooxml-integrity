# A Python document tool for the review-history benchmark, installed only from
# a hashed lock (tool.lock, generated once with uv 0.12.20 and committed beside
# this file). The network is used only while building.
FROM python@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f

COPY tool.lock /tool.lock
RUN pip install --no-cache-dir --root-user-action=ignore --require-hashes --no-deps -r /tool.lock \
 && pip freeze > /freeze.txt
