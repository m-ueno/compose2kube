# pod controller
input3 = """
services:
  db:
    image: postgres:13.9-bullseye
    restart: always
    environment:
      POSTGRES_PASSWORD: postgres
    expose:
      - "5432"
    volumes:
      - db_data:/var/lib/postgresql/data
  bff:
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/db
      - DATASET_SELECT_MODE=${DATASET_SELECT_MODE:?err}
      - UPLOAD_DIR=/user_experiment
    env_file:
      - .env
    image: ml-webapp-api
    restart: always
    ports:
      - "10999"
    volumes:
      - type: volume
        source: user_experiment
        target: /user_experiment
volumes:
  db_data:
"""

input4 = """
services:
  web:
    image: $IMAGE_REGISTRY/$IMAGE_REPOSITORY:$IMAGE_VERSION
    container_name: rule-editor
    # user: '${UID}:${GID}'
    restart: always
    environment:
      - http_proxy=$IMAGE_PROXY
      - HTTP_PROXY=$IMAGE_PROXY
      - https_proxy=$IMAGE_PROXY
      - HTTPS_PROXY=$IMAGE_PROXY
      - TZ=Asia/Tokyo
    ports:
      - $IMAGE_PORT:10081
    command: ["sh", "/workspace/analyzer-web/compose_entrypoint.sh"]
"""


input5 = """services:
  act-sdk_exec:
    image: ${REGISTRY}/${REPOSITORY}/${MAIN_EXEC_IMAGE}
    tty: true
    restart: always
    ports:
      - "${GUI_FWD_PORT}:8002" # serverアプリとの通信
      - "${WSS_FWD_PORT}:5003" # Websocketとの通信
    depends_on:
      - act-sdk_app
    environment:
      PYTHONPATH: /workspace/app-base/src:/workspace
    volumes:
      - workspace_app:/workspace/app
      - ./log:/workspace/app/exec/log
      - ./app_container/src:/workspace/app/src
      - ./app_container/configs:/workspace/app/exec/configs
      - ./add_components/websocket_sv:/workspace/app-base/src/app_base/parts/websocket_sv
    cap_add:
      - SYS_ADMIN
    security_opt:
      - seccomp:unconfined
    entrypoint: "/bin/sh -c ' cd /workspace/app/src && python3 SampleApp.py '"
volumes:
  workspace_app:
"""

input9 = input4

input12 = """
services:
  notebook:
    ports:
      - "8888"
    image: ml-webapp-runner
    restart: always
    healthcheck:
      test:
        [
          "CMD-SHELL",
          "wget -O - http://127.0.0.1:8888/jupyter/lab || exit 1"
        ]
      start_period: "10s"
      retries: 3
      timeout: "5s"
      interval: "30s"
"""


# @dataclass
# class Example:
#     input: str
#     ok: str
#     ng: str | None = None


# EXAMPLES = [
#     # ex5
#     Example(
#         input="""services:
#   act-sdk_exec:
#     image: ${REGISTRY}/${REPOSITORY}/${MAIN_EXEC_IMAGE}
#     tty: true
#     restart: always
#     ports:
#       - "${GUI_FWD_PORT}:8002" # serverアプリとの通信""",
#         ok="""apiVersion: v1
# kind: Service
# metadata:
#   name: act-sdk-exec
# """,
#     ),
#     # ex9
#     Example(
#         input="""services:
#   web:
#     image: $IMAGE_REGISTRY/$IMAGE_REPOSITORY:$IMAGE_VERSION
#     # user: '${UID}:${GID}'
# """,
#         ok="""containers:
#         - name: web
#           image: $IMAGE_REGISTRY/$IMAGE_REPOSITORY:$IMAGE_VERSION
#           # Uncomment the following lines if you want to set the user
#           # securityContext:
#           #   runAsUser: ${UID}
#           #   runAsGroup: ${GID}
# """,
#     ),
#     # ex12
#     Example(
#         input="""services:
#   notebook:
#     ports:
#       - "8888"
#     image: ml-webapp-runner
#     restart: always
#     healthcheck:
#       test:
#         [
#           "CMD-SHELL",
#           "wget -O - http://127.0.0.1:8888/jupyter/lab || exit 1"
#         ]
#       start_period: "10s"
#       retries: 3
#       timeout: "5s"
#       interval: "30s"
# """,
#         ok="""
# apiVersion: v1
# kind: Service
# metadata:
#   name: notebook
# spec:
#   ports:
#     - protocol: TCP
#       port: 8888
# ---
# apiVersion: apps/v1
# kind: Deployment
# metadata:
#   name: notebook
# spec:
#   replicas: 1
#   selector:
#     matchLabels:
#       app: notebook
#   template:
#     metadata:
#       labels:
#         app: notebook
#     spec:
#       containers:
#         - name: notebook
#           image: ml-webapp-runner
#           ports:
#             - containerPort: 8888
#           livenessProbe:
#             httpGet:
#               path: /jupyter/lab
#               port: 8888
#             initialDelaySeconds: 10
#             periodSeconds: 30
#             failureThreshold: 3
#           restartPolicy: Always
# """,
#     ),
# ]
