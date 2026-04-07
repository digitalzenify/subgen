FROM python:3.12-slim

COPY requirements.txt entrypoint.sh /

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg gosu tzdata \
    && pip install --no-cache-dir -r /requirements.txt \
    && apt-get purge -y --auto-remove \
    && rm -rf /var/lib/apt/lists/* /tmp/*

WORKDIR /subgen

COPY launcher.py subgen.py language_code.py /subgen/

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python3", "launcher.py"]
