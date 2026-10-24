FROM python:3.12-slim
RUN python -m pip install --no-cache-dir pytest==8.4.2 PyYAML==6.0.3 httpx==0.28.1 jsonschema==4.25.1 tomli==2.0.1
ENV PYTHONUTF8=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /evaluation
ENTRYPOINT ["python"]
