FROM python:3.12-slim AS build
WORKDIR /build
COPY pyproject.toml README.md LICENSE ./
COPY src/ src/
COPY schemas/ schemas/
RUN pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 BACKLOGER_PROJECT=/project
RUN apt-get update && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
RUN groupadd --gid 10001 backloger && useradd --uid 10001 --gid 10001 --no-create-home backloger
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels backloger && rm -rf /wheels
USER 10001:10001
WORKDIR /project
EXPOSE 8765
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=3)"]
ENTRYPOINT ["backloger", "--project", "/project"]
CMD ["serve", "--host", "0.0.0.0", "--allow-remote", "--port", "8765"]
