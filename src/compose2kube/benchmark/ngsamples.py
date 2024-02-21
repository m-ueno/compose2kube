import json
import re
from dataclasses import dataclass
from operator import itemgetter
from typing import Any, Optional

import marko
import marko.inline
import yaml
from langchain.cache import SQLiteCache
from langchain.chains.openai_functions import (
    convert_to_openai_function,
    get_openai_output_parser,
)
from langchain.globals import set_llm_cache
from langchain.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import (
    ConfigurableField,
    RunnableConfig,
    RunnableLambda,
    RunnablePassthrough,
)
from langchain_core.runnables import chain as chain_decorator
from langfuse.callback import CallbackHandler

from compose2kube.evaluator import Manifests
from compose2kube.model import ChatOpenAIMultiGenerations

set_llm_cache(SQLiteCache())


class MDCodeBlockOutputParser(StrOutputParser):
    def parse(self, text: str) -> str:
        if "```" not in text:
            return text
        if "```yaml" not in text:
            # Found the start of a code block (```), but the end is missing.
            # Then, just delete it.
            return text.replace("```", "")
        doc = marko.parse(text)
        for element in doc.children:
            if isinstance(element, marko.block.FencedCode):
                assert isinstance(element.children[0], marko.inline.RawText)
                return element.children[0].children
        raise ValueError("the text contains ``` but not match any codeblock" + text)


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


@dataclass
class Example:
    input: str
    ok: str
    ng: str | None = None


EXAMPLES = [
    # ex5
    Example(
        input="""services:
  act-sdk_exec:
    image: ${REGISTRY}/${REPOSITORY}/${MAIN_EXEC_IMAGE}
    tty: true
    restart: always
    ports:
      - "${GUI_FWD_PORT}:8002" # serverアプリとの通信""",
        ok="""apiVersion: v1
kind: Service
metadata:
  name: act-sdk-exec
""",
    ),
    # ex9
    Example(
        input="""services:
  web:
    image: $IMAGE_REGISTRY/$IMAGE_REPOSITORY:$IMAGE_VERSION
    # user: '${UID}:${GID}'
""",
        ok="""containers:
        - name: web
          image: $IMAGE_REGISTRY/$IMAGE_REPOSITORY:$IMAGE_VERSION
          # Uncomment the following lines if you want to set the user
          # securityContext:
          #   runAsUser: ${UID}
          #   runAsGroup: ${GID}
""",
    ),
    # ex12
    Example(
        input="""services:
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
""",
        ok="""
apiVersion: v1
kind: Service
metadata:
  name: notebook
spec:
  ports:
    - protocol: TCP
      port: 8888
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: notebook
spec:
  replicas: 1
  selector:
    matchLabels:
      app: notebook
  template:
    metadata:
      labels:
        app: notebook
    spec:
      containers:
        - name: notebook
          image: ml-webapp-runner
          ports:
            - containerPort: 8888
          livenessProbe:
            httpGet:
              path: /jupyter/lab
              port: 8888
            initialDelaySeconds: 10
            periodSeconds: 30
            failureThreshold: 3
          restartPolicy: Always
""",
    ),
]


@dataclass
class Judgement:
    ok: bool
    metadata: dict[str, Any]

    def to_json(self, *args, **kwargs):
        return json.dumps(self.__dict__)


def judge3(manifests_str: str) -> Judgement:
    try:
        manifests = yaml.safe_load_all(manifests_str)
        for manifest in manifests:
            if manifest.get("kind") == "Service":
                continue
            if manifest.get("metadata", {}).get("name") == "db":
                controller_kind = manifest.get("kind")
                ok = controller_kind == "StatefulSet"
                return Judgement(ok=ok, metadata=dict(kind=controller_kind))
    except yaml.YAMLError as exc:
        print(f"Error parsing YAML: {exc}")
        return Judgement(ok=False, metadata={"error": str(exc)})

    return Judgement(
        ok=False, metadata={"error": "No 'db' manifest found or other error"}
    )


def judge4_easy(manifests: str) -> Judgement:
    for line in manifests.splitlines():
        if line.strip() == "image: $IMAGE_REGISTRY/$IMAGE_REPOSITORY:$IMAGE_VERSION":
            return Judgement(ok=True, metadata={"message": "Correct image"})
    return Judgement(ok=False, metadata={"message": "expected image string not found"})


def judge4(manifests: str) -> Judgement:
    try:
        documents = yaml.safe_load_all(manifests)
        for doc in documents:
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
    except Exception as e:
        return Judgement(ok=False, metadata={"error": str(e)})


def judge5(manifests: str) -> Judgement:
    def is_valid_dns_name(name: str) -> bool:
        """Check if the given string is a valid DNS name."""
        if re.match(r"^[a-zA-Z0-9-]{1,63}(\.[a-zA-Z0-9-]{1,63})*$", name):
            return True
        return False

    try:
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
    except Exception as e:
        return Judgement(ok=False, metadata={"error": e})


def judge12(manifests: str) -> Judgement:
    try:
        documents = yaml.safe_load_all(manifests)
        for doc in documents:
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
                "probe": probe,
            },
        )
    except Exception as e:
        return Judgement(ok=False, metadata={"error": str(e)})


def judge9(manifests: str) -> Judgement:
    # pyyamlでパースするとコメントが消えてしまうので文字列処理
    import re

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


def wrap(fn):
    @chain_decorator
    def wrapped_fn(arg):
        try:
            return fn(arg)
        except Exception as e:
            return Judgement(ok=False, metadata={"error": str(e)})

    return wrapped_fn


@chain_decorator
def tap_print(x):
    print("tap:", x)
    return x


@chain_decorator
def identity(x):
    return x


def _join_manifests(xs: list[dict | str]) -> str:
    # compose.llm.Manifests.manifests: list[str|dict] にした結果のその場しのぎの関数
    child = xs[0]
    if isinstance(child, dict):
        return yaml.safe_dump_all(xs)
    elif isinstance(child, str):
        return "\n---\n".join(xs)  # type:ignore
    else:
        raise ValueError(f"argument must be list[dit|str]: {xs}")


CHAINS = {
    #
    # chain 1
    #
    # receives {compose: str, judge: Callable}
    "zeroshot-txt": RunnablePassthrough.assign(
        output={"compose": itemgetter("compose")}
        | PromptTemplate.from_template(
            "convert the composefile to kubernetes manifests:\n{compose}"
        )
        | ChatOpenAIMultiGenerations(cache=True).configurable_fields(
            model_name=ConfigurableField(id="model_name"),
            n=ConfigurableField(id="n", name="llm_n"),
        )
    )
    .assign(  # {compose, judge, output}
        output_str=itemgetter("output") | StrOutputParser().map(),
        output_md=itemgetter("output") | MDCodeBlockOutputParser().map(),
    )
    .assign(  # {compose, judge, output, output_str, output_md}
        judged=RunnableLambda(lambda dic: list(map(dic["judge"], dic["output_md"])))
    )
    .with_config(run_name="zeroshot-txt", callbacks=[CallbackHandler()]),
    #
    # chain2
    "zeroshot-jsonmode": RunnablePassthrough.assign(
        output={"compose": itemgetter("compose")}
        | PromptTemplate.from_template(
            "convert the composefile to kubernetes manifests:\n{{compose}}",
            template_format="jinja2",
        )
        | ChatOpenAIMultiGenerations(
            cache=True,
            model_kwargs={
                "seed": 1,
                "functions": [convert_to_openai_function(Manifests)],
                "function_call": {"name": "Manifests"},
            },
        ).configurable_fields(
            model_name=ConfigurableField(id="model_name"),
            n=ConfigurableField(id="n", name="llm_n"),
        )
    )
    .assign(  # {compose, judge, output}
        output_json=itemgetter("output")
        | (
            get_openai_output_parser([Manifests])
            | (lambda m: m.manifests)
            | _join_manifests
        )
        .with_fallbacks([RunnableLambda(lambda _: "parse failed")])
        .map(),
    )
    .assign(  # {compose, judge, output, output_json}
        judged=RunnableLambda(lambda dic: list(map(dic["judge"], dic["output_json"])))
    )
    .with_fallbacks([identity]),
}


def convert_and_judge_examples(llm_kwargs={}):
    results = {}
    prompt = PromptTemplate.from_template(
        "convert the composefile to kubernetes manifests:\n{compose}"
    )
    chat = ChatOpenAIMultiGenerations(cache=True, **llm_kwargs)
    for name, input, judge in INPUTS_JUDGES:

        def wrap(fn):
            @chain_decorator
            def wrapped_fn(arg):
                try:
                    return fn(arg)
                except Exception as e:
                    return Judgement(ok=False, metadata={"error": str(e)})

            return wrapped_fn

        chain = (
            {"compose": RunnablePassthrough()}
            | prompt
            | chat
            | dict(
                converted=StrOutputParser().map(),
                judge=(MDCodeBlockOutputParser() | wrap(judge)).map(),
            )
        ).with_config(config=RunnableConfig(callbacks=[CallbackHandler()]))
        got = chain.invoke(input)
        results[name] = got

    return results


__all__ = ["convert_and_judge_examples"]
