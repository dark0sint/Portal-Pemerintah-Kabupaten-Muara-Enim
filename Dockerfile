FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN useradd -r -u 10001 portal
WORKDIR /srv/portal-muaraenim
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
COPY gunicorn.conf.py .
RUN mkdir -p instance && chown -R portal:portal instance
USER portal
ENV INSTANCE_DIR=/srv/portal-muaraenim/instance
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz')" || exit 1
CMD ["gunicorn", "-c", "gunicorn.conf.py", "-b", "0.0.0.0:8000", "app:app"]
