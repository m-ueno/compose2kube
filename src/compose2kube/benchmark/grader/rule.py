import re

import yaml

from .judgement import Judgement

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


def catch_decorator(fn):
    def wrapped_fn(*args):
        try:
            return fn(*args)
        except Exception as e:
            return Judgement(ok=False, metadata={"error": str(e)})

    return wrapped_fn


@catch_decorator
def judge3(manifests_str: str) -> Judgement:
    try:
        manifests = yaml.safe_load_all(manifests_str)
        for manifest in manifests:
            if manifest is None:
                continue
            if manifest.get("kind") == "Service":
                continue
            if manifest.get("metadata", {}).get("name") == "db":
                controller_kind = manifest.get("kind")
                ok = controller_kind == "StatefulSet"
                return Judgement(ok=ok, metadata=dict(kind=controller_kind))
    except Exception as exc:
        print(f"Error parsing YAML: {exc}")
        return Judgement(ok=False, metadata={"error": str(exc)})

    return Judgement(
        ok=False, metadata={"reason": "No 'db' manifest found or other error"}
    )


def judge4_easy(manifests: str) -> Judgement:
    for line in manifests.splitlines():
        if line.strip() == "image: $IMAGE_REGISTRY/$IMAGE_REPOSITORY:$IMAGE_VERSION":
            return Judgement(ok=True, metadata={"message": "Correct image"})
    return Judgement(ok=False, metadata={"message": "expected image string not found"})


@catch_decorator
def judge4(manifests: str) -> Judgement:
    documents = yaml.safe_load_all(manifests)
    for doc in documents:
        if doc is None:
            continue
        match doc.get("kind", ""):
            case "Deployment" | "StatefulSet":
                containers = (
                    doc.get("spec", {})
                    .get("template", {})
                    .get("spec", {})
                    .get("containers", [])
                )

            case "Pod":
                containers = doc.get("spec", {}).get("containers", {})
            case _:
                continue
        for container in containers:
            image = container.get("image", "")
            env_vars = container.get("env", [])
            if image == "$IMAGE_REGISTRY/$IMAGE_REPOSITORY:$IMAGE_VERSION":
                return Judgement(ok=True, metadata={"env": env_vars})

    return Judgement(ok=False, metadata={"message": "Incorrect image"})


@catch_decorator
def judge5(manifests: str) -> Judgement:
    def is_valid_dns_name(name: str) -> bool:
        """Check if the given string is a valid DNS name."""
        if re.match(r"^[a-zA-Z0-9-]{1,63}(\.[a-zA-Z0-9-]{1,63})*$", name):
            return True
        return False

    documents = yaml.safe_load_all(manifests)

    at_least_one_service_name_is_valid = False
    for doc in documents:
        if doc is None:
            continue
        if not isinstance(doc, dict):
            raise ValueError(f"YAML parsed non dict: {doc}")
        if doc.get("kind", "") == "Service":
            metadata_name = doc.get("metadata", {}).get("name", "")
            if is_valid_dns_name(metadata_name):
                at_least_one_service_name_is_valid = True
            else:
                return Judgement(
                    ok=False,
                    metadata={"message": f"Invalid DNS name: {metadata_name}"},
                )
    return Judgement(
        ok=at_least_one_service_name_is_valid,
        metadata={
            "message": "At least one service name is valid"
            if at_least_one_service_name_is_valid
            else "No service found"
        },
    )


@catch_decorator
def judge12(manifests: str) -> Judgement:
    documents = yaml.safe_load_all(manifests)
    for doc in documents:
        if doc is None:
            continue
        match doc.get("kind"):
            case "Deployment" | "StatefulSet":
                containers = (
                    doc.get("spec", {})
                    .get("template", {})
                    .get("spec", {})
                    .get("containers", [])
                )
            case "Pod":
                containers = doc.get("spec", {}).get("containers", [])
            case _:
                continue
        for container in containers:
            for probe_type in ["livenessProbe", "readinessProbe"]:
                probe = container.get(probe_type, {})
                if probe.get("httpGet", {}).get("path", "") == "/jupyter/lab":
                    return Judgement(
                        ok=True,
                        metadata=dict(probe=probe),
                    )
    return Judgement(
        ok=False,
        metadata={
            "message": "No probe with /jupyter/lab found",
            "probe": probe if "probe" in locals() else None,
        },
    )


def judge9(manifests: str) -> Judgement:
    # pyyamlでパースするとコメントが消えてしまうので文字列処理

    required_comments = list(
        map(
            re.compile,
            [
                r"#\s+securityContext:",
                r"#\s+runAsUser:\s+\${UID}",
                r"#\s+runAsGroup:\s+\${GID}",
            ],
        )
    )

    # Check if all required comments are present in the manifests string
    comments_present = all(
        re.search(pattern, manifests) for pattern in required_comments
    )
    if comments_present:
        return Judgement(
            ok=True, metadata={"message": "All required comments are included."}
        )
    else:
        return Judgement(
            ok=False, metadata={"message": "Not all required comments are included."}
        )


INPUTS_JUDGES = [
    ("input3", input3, judge3),
    ("input4", input4, judge4),
    ("input5", input5, judge5),
    ("input9", input9, judge9),
    ("input12", input12, judge12),
]
