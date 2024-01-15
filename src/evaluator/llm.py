import inspect
import unittest
import yaml
from collections import Counter

from dotenv import load_dotenv, find_dotenv
from langchain.cache import SQLiteCache
from langchain.callbacks.tracers import ConsoleCallbackHandler
from langchain.chains.openai_functions import convert_to_openai_function
from langchain.chains.openai_functions import get_openai_output_parser
from langchain.chat_models import ChatOpenAI
from langchain.globals import set_llm_cache
from langchain.prompts import BasePromptTemplate
from langchain.prompts import ChatPromptTemplate
from langchain.pydantic_v1 import BaseModel, Field


load_dotenv(find_dotenv())
set_llm_cache(SQLiteCache(database_path=".langchain.db"))

GPT4TURBO = "gpt-4-1106-preview"


class Manifests(BaseModel):
    """Kubernetes manifests container"""

    manifests: list[str] = Field(
        description="list of YAML manifests. each manifest is a valid YAML file per API object"
    )

    def report(self) -> dict[str, int]:
        api_objects = []
        for m in self.manifests:
            api_objects += list(yaml.safe_load_all(m))

        kinds = [api.get("kind") for api in api_objects]
        svc_types = [
            f"svc/{api['spec'].get('type')}"
            for api in api_objects
            if api.get("kind") == "Service"
        ]
        # TODO? cout "spec.template.spec.containers[].livenssProbe"
        # probes = 0
        # for api in api_objects:
        #     if api.get("kind") != "Deployment" or api.get("spec") is None:
        #         continue
        #     if api["spec"].get("livenessProbe"):
        #         probes += 1

        return {**Counter(kinds), **Counter(svc_types)}

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


class Compose(BaseModel):
    """docker compose spec"""

    spec: str = Field(
        description="A string of the contents of a Compose file that satisfies the latest specifications"
    )


prompt1_for_kompose = ChatPromptTemplate.from_messages(
    [
        # (
        #     "system",
        #     "You are a skillful devops engineer.",
        # ),
        (
            "human",
            inspect.cleandoc(
                """
            Please annotate the input compose file with appropriate labels for Kompose.

            The output from Kompose will later be deployed to an {target} environment.
            Be sure to apply labels that will allow it to function properly in the deployment environment.

            if you want inform us something, make it inline comment inside yaml.

            ###References###

            here are storageclasses in the target environment:
            ---
            apiVersion: storage.k8s.io/v1
            kind: StorageClass
            metadata:
            name: efs-sc
            provisioner: efs.csi.aws.com
            ---

            kompose supports Kompose-specific labels within the docker-compose.yml file to explicitly define the generated resources’ behavior upon conversion, like Service, PersistentVolumeClaim…

The currently supported options are:

Key	Value
kompose.service.type	nodeport / clusterip / loadbalancer / headless
kompose.service.group	name to group the containers contained in a single pod
kompose.service.expose	true / hostnames (separated by comma)
kompose.service.nodeport.port	port value (string)
kompose.service.expose.tls-secret	secret name
kompose.service.expose.ingress-class-name	ingress class name
kompose.volume.size	kubernetes supported volume size
kompose.volume.storage-class-name	kubernetes supported volume storageClassName
kompose.volume.type	use k8s volume type, eg “configMap”, “persistentVolumeClaim”, “emptyDir”, “hostPath”
kompose.controller.type	deployment / daemonset / replicationcontroller / statefulset
kompose.image-pull-policy	kubernetes pods imagePullPolicy
kompose.image-pull-secret	kubernetes secret name for imagePullSecrets
kompose.service.healthcheck.readiness.disable	kubernetes readiness disable
kompose.service.healthcheck.readiness.test	kubernetes readiness exec command
kompose.service.healthcheck.readiness.http_get_path	kubernetes readiness httpGet path
kompose.service.healthcheck.readiness.http_get_port	kubernetes readiness httpGet port
kompose.service.healthcheck.readiness.tcp_port	kubernetes readiness tcpSocket port
kompose.service.healthcheck.readiness.interval	kubernetes readiness interval value
kompose.service.healthcheck.readiness.timeout	kubernetes readiness timeout value
kompose.service.healthcheck.readiness.retries	kubernetes readiness retries value
kompose.service.healthcheck.readiness.start_period	kubernetes readiness start_period
kompose.service.healthcheck.liveness.http_get_path	kubernetes liveness httpGet path
kompose.service.healthcheck.liveness.http_get_port	kubernetes liveness httpGet port
kompose.service.healthcheck.liveness.tcp_port	kubernetes liveness tcpSocket port
kompose.service.external-traffic-policy	‘cluster’, ‘local’, ‘’
kompose.security-context.fsgroup	kubernetes pod security group fsgroup
kompose.volume.sub-path	kubernetes volume mount subpath
            """
            ),
        ),
        (
            "human",
            "Make calls to the relevant function to record the entities in the following input: ```{input}```",
        ),
        ("human", "Tip: Make sure to answer in the correct format"),
    ]
)

prompt_zeroshot = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a skillful devops engineer. Please output kubenetes manifest corresponding to the given files.",
        ),
        (
            "human",
            "Make calls to the relevant function to record the entities in the following input: ```{input}```",
        ),
        ("human", "Tip: Make sure to answer in the correct format"),
        (
            "human",
            inspect.cleandoc(
                """Note: Make sure the output manifests work in {target} environment.

            if you want inform us something, make it inline comment inside yaml.

            ###REFERENCE###
            here are storageclasses in the target environment:
            ---
            apiVersion: storage.k8s.io/v1
            kind: StorageClass
            metadata:
            name: efs-sc
            provisioner: efs.csi.aws.com
            ---
            """
            ),
        ),
    ]
)

"""
            # Output the following kube resources:
            # - Service
            # - Deployment
            # - PVC (if necessary)
"""


def make_chain(
    prompt: BasePromptTemplate,
    model: str,
    seed: int | None,
    temperature: float,
    cache: bool,
    tools: list,
    n: int = 1,
):
    llm = ChatOpenAI(
        model=model,
        cache=cache,
        n=n,
        temperature=temperature,
        verbose=True,
        model_kwargs={"seed": seed},
    )
    openai_functions = [convert_to_openai_function(f) for f in tools]
    llm_kwargs = {"functions": openai_functions}
    if len(openai_functions) == 1:
        llm_kwargs["function_call"] = {"name": openai_functions[0]["name"]}  # type: ignore
    output_parser = get_openai_output_parser(tools)
    return prompt | llm.bind(**llm_kwargs) | output_parser


def make_chain_n(
    template: ChatPromptTemplate,
    content: str,
    model: str,
    seed: int | None,
    tools: list,
    n: int,
) -> list:
    """
    generate_n(prompt) -> list[string]
    """
    msgs = template.format_messages(input=content, target="AWS EKS")
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

    resp = llm2.generate([msgs])
    parsed = []
    for gen in resp.generations[0]:
        try:
            parsed.append(output_parser.invoke(gen.message))  # type: ignore
        except Exception as e:
            print("output parser failed", e)
            parsed.append({})

    return parsed


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
