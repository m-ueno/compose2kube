FROM python:3.9-slim
RUN --mount=type=cache,target=/root/.cache/pip pip install \
    psycopg2-binary \
    requests \
    websocket-client
WORKDIR /app
COPY ./receive_pg.py /app
CMD ["python","-u","/app/receive_pg.py"]
