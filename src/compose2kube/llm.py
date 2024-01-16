import inspect
import subprocess
import tempfile
import unittest
import yaml
from collections import Counter

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

from compose2kube.templates import prompt1_for_kompose, prompt_zeroshot


load_dotenv(find_dotenv())
set_llm_cache(SQLiteCache(database_path=".langchain.db"))

GPT4TURBO = "gpt-4-1106-preview"
GPT35TURBO = "gpt-3.5-turbo"


class Manifests(BaseModel):
    """Kubernetes manifests container"""

    manifests: list[str] = Field(
        description="list of YAML manifests. each manifest is a valid YAML file per API object"
    )

    # def report(self) -> dict[str, int]:
    #     api_objects = []
    #     for m in self.manifests:
    #         api_objects += list(yaml.safe_load_all(m))

    #     kinds = [api.get("kind") for api in api_objects]
    #     svc_types = [
    #         f"svc/{api['spec'].get('type')}"
    #         for api in api_objects
    #         if api.get("kind") == "Service"
    #     ]
    #     return {**Counter(kinds), **Counter(svc_types)}

    @classmethod
    def from_file(cls, name: str):
        with open(name) as f:
            m = f.read()
        return Manifests(manifests=[m])

    def canparse(self) -> bool:
        try:
            _ = yaml.safe_load_all(self.join())
            return True
        except:
            return False

    def join(self) -> str:
        """Returns a single yaml string"""

        return "---\n".join(self.manifests)

    def dry_run(self, server: bool) -> tuple[bool, str]:
        try:
            dryrun_opt = "client"
            if server:
                dryrun_opt = "server"

            with tempfile.NamedTemporaryFile(
                "w", prefix="genmani", suffix=".yaml", delete=False
            ) as f:
                f.write(self.join())
                f.close()
                cmd = f"microk8s.kubectl apply -f {f.name} --dry-run={dryrun_opt}"
                got = subprocess.check_output(
                    cmd, shell=True, universal_newlines=True, stderr=subprocess.STDOUT
                )
                return True, got
        except subprocess.CalledProcessError as e:
            return False, e.output

    def feature(self) -> dict[str, int]:
        # マニフェストの「特徴量」を抽出する
        api_objects = list(yaml.safe_load_all(self.join()))
        api_objects = filter(lambda x: x is not None, api_objects)

        kinds = [api.get("kind") for api in api_objects]
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


#
# tools&prompt -> prompt|llm(tools) -> parser(tools) -> Toolのclass
# chain1 = prompt.bind(context="") | kompose
# chain2 = prompt | llm(tools1) | kompose | parse
# chain3 = prompt | llm(tools2) | parse(tools2)
#


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
