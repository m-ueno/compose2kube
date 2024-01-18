import inspect
import subprocess
import tempfile
from typing import Any
import unittest
import yaml
from collections import Counter
from logging import getLogger

from dotenv import load_dotenv, find_dotenv
from langchain_openai import ChatOpenAI
from langchain.cache import SQLiteCache
from langchain.callbacks.tracers import ConsoleCallbackHandler
from langchain.chains.openai_functions import convert_to_openai_function
from langchain.chains.openai_functions import get_openai_output_parser
from langchain.globals import set_llm_cache
from langchain_core.prompt_values import PromptValue
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.runnables import (
    Runnable,
    RunnableLambda,
    RunnableParallel,
    RunnablePassthrough,
    chain as chain_decorator,
)
import glom
import joblib

from compose2kube.templates import prompt1_for_kompose, prompt_zeroshot


load_dotenv(find_dotenv())
set_llm_cache(SQLiteCache(database_path=".langchain.db"))
logger = getLogger(__name__)
joblib_cachedir = "/tmp/joblibcache"
memory = joblib.Memory(joblib_cachedir, compress=True)

GPT4TURBO = "gpt-4-1106-preview"
GPT35TURBO = "gpt-3.5-turbo"


@memory.cache
def _dry_run(spec: str, server: bool) -> tuple[bool, str]:
    dryrun_opt = "client"
    if server:
        dryrun_opt = "server"

    try:
        with tempfile.NamedTemporaryFile(
            "w", prefix="genmani", suffix=".yaml", delete=False
        ) as f:
            f.write(spec)
            f.close()
            cmd = f"microk8s.kubectl apply -f {f.name} --dry-run={dryrun_opt}"
            got = subprocess.check_output(
                cmd, shell=True, universal_newlines=True, stderr=subprocess.STDOUT
            )
            return True, got
    except subprocess.CalledProcessError as e:
        return False, e.output


class Manifests(BaseModel):
    """Kubernetes manifests container. Generated and human written."""

    manifests: list[str] = Field(
        description="list of YAML manifests. each manifest is a valid YAML file per API object"
    )

    @classmethod
    def from_file(cls, name: str):
        with open(name) as f:
            m = f.read()
        return Manifests(manifests=[m])

    def join(self) -> str:
        """Returns a single yaml string"""

        return "---\n".join(self.manifests)

    def feature(self) -> dict[str, Any]:
        # マニフェストの特徴抽出
        dry_run_client_success, client_msg = self.dry_run(False)
        dry_run_server_success, server_msg = self.dry_run(True)
        line_length = len(self.join().splitlines())
        return dict(
            line_length=line_length,
            dry_run_client_success=dry_run_client_success,
            client_msg=client_msg,
            dry_run_server_success=dry_run_server_success,
            server_msg=server_msg,
            **self.count(),
        )

    def dry_run(self, server: bool) -> tuple[bool, str]:
        return _dry_run(spec=self.join(), server=server)

    def count(self) -> dict[str, int]:
        # count api objects
        api_objects = []
        try:
            api_objects = list(yaml.full_load_all(self.join()))
        except Exception as e:
            logger.error(e)
        api_objects = filter(lambda x: x is not None, api_objects)

        kinds: list[str] = [
            api.get("kind") for api in api_objects if isinstance(api, dict)
        ]
        # svc_types = [
        #     f"svc/{api['spec'].get('type')}"
        #     for api in api_objects
        #     if api.get("kind") == "Service"
        # ]

        # count "spec.template.spec.containers[].livenessProbe"

        n_containers = 0
        livenessProbe = 0
        readinessProbe = 0

        for api in api_objects:
            containers = glom.glom(api, "spec.template.spec.containers", default=[])
            for c in containers:
                if c.get("livenessProbe"):
                    livenessProbe += 1
                if c.get("readinessProbe"):
                    readinessProbe += 1
            n_containers += len(containers)

        return {
            **Counter(kinds),
            "livenessProbe": livenessProbe,
            "readinessProbe": readinessProbe,
            "n_containers": n_containers,
        }


class Compose(BaseModel):
    """docker compose spec"""

    spec: str = Field(
        description="A string of the contents of a Compose file that satisfies the latest specifications"
    )


def make_llm_runnable(tools, n: int, model: str, seed=1) -> Runnable:
    """use generate() instead of .invoke() to get n>1 generations"""

    openai_functions = [convert_to_openai_function(f) for f in tools]
    llm2 = ChatOpenAI(
        model=model,
        cache=True,
        temperature=0.8,
        verbose=True,
        n=n,
        model_kwargs={
            "seed": seed,
            "functions": openai_functions,
            "function_call": {"name": openai_functions[0]["name"]},
        },
    )

    output_parser = get_openai_output_parser(tools)

    @chain_decorator
    def myllm(text: PromptValue) -> list[Manifests]:
        msgs = text.to_messages()

        llmresult = llm2.generate([msgs])
        messages = [gen.message for gen in llmresult.generations[0]]  # type: ignore

        parsed = []
        for msg in messages:
            try:
                parsed.append(output_parser.invoke(msg))
            except Exception as e:
                print("output parser failed", e)
                parsed.append({})

        return parsed

    return myllm


class TestLLM(unittest.TestCase):
    def test_generate_n(self):
        content = """
        version: '3.8'
        services:
          web:
            build: .
            ports:
              - "5000:5000"
            volumes:
              - .:/code
            environment:
              FLASK_ENV: development
        """
        n = 2
        parsed = make_chain_n(
            prompt_zeroshot, content, GPT4TURBO, None, tools=[Manifests], n=n
        )
        self.assertEqual(len(parsed), n)
        with self.assertRaises(AssertionError):
            self.assertListEqual(parsed[0].manifests, parsed[1].manifests)
