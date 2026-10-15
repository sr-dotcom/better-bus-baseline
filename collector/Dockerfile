FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 collector \
    && mkdir /data \
    && chown collector /data

WORKDIR /app
COPY collect.py .

USER collector
VOLUME /data
CMD ["python", "-u", "collect.py"]
