FROM python:3.12-slim
ARG CODEX_VERSION=0.163.0-alpha.10.2
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm git ripgrep bubblewrap \
    && rm -rf /var/lib/apt/lists/* \
    && npm install --global @openai/codex@${CODEX_VERSION} \
    && python -m pip install --no-cache-dir pytest==8.4.2 PyYAML==6.0.3 httpx==0.28.1 jsonschema==4.25.1 tomli==2.0.1
ENV PYTHONUTF8=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 CODEX_HOME=/scope-home
LABEL scope.natural-solver="official-cli-only" scope.codex-version="0.163.0-alpha.10.2"
WORKDIR /product
ENTRYPOINT ["codex"]
