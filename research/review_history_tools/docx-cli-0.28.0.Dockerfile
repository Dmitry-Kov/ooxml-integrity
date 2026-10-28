# docx-cli (npm bun-docx 0.28.0, MIT; repository kklimuk/docx-cli tag v0.28.0) for the
# review-history recheck (evidence/review-history-recheck). Built exactly as the
# frozen benchmark's docx-cli.Dockerfile, with the new release: dist/index.js is
# a self-contained bundle (Node/Bun built-ins only), so the published tarball,
# checked by SHA-256, is all it needs.
# Build context: bun-docx-0.28.0.tgz from https://registry.npmjs.org/bun-docx/-/bun-docx-0.28.0.tgz.
FROM oven/bun@sha256:e10577f0db68676a7024391c6e5cb4b879ebd17188ab750cf10024a6d700e5c4

COPY bun-docx-0.28.0.tgz /opt/bun-docx-0.28.0.tgz
RUN echo "11c6e900146ff2b3f561d1ef7660db90e6d5b6d25544e7969a1bc47919abd9fc  /opt/bun-docx-0.28.0.tgz" | sha256sum -c - \
 && mkdir -p /opt/docx && tar -xzf /opt/bun-docx-0.28.0.tgz -C /opt/docx && rm /opt/bun-docx-0.28.0.tgz \
 && chmod -R a+rX /opt/docx && bun /opt/docx/package/dist/index.js --version
