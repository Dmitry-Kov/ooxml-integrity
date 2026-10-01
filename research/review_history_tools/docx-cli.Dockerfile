# docx-cli (npm bun-docx 0.26.0, MIT; repository kklimuk/docx-cli tag v0.26.0) for the
# review-history benchmark. dist/index.js is a self-contained bundle (Node/Bun
# built-ins only), so the published tarball, checked by SHA-256, is all it needs.
# Build context: bun-docx-0.26.0.tgz from `npm pack bun-docx@0.26.0`.
FROM oven/bun@sha256:e10577f0db68676a7024391c6e5cb4b879ebd17188ab750cf10024a6d700e5c4

COPY bun-docx-0.26.0.tgz /opt/bun-docx-0.26.0.tgz
RUN echo "a65a9a171b291fecc4ef8f45fcb9c764a891ef92d7c81b473ce99e58b51ad705  /opt/bun-docx-0.26.0.tgz" | sha256sum -c - \
 && mkdir -p /opt/docx && tar -xzf /opt/bun-docx-0.26.0.tgz -C /opt/docx && rm /opt/bun-docx-0.26.0.tgz \
 && chmod -R a+rX /opt/docx && bun /opt/docx/package/dist/index.js --version
