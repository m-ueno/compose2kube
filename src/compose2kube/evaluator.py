import logging
import subprocess
from operator import itemgetter
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import cast

import yaml
from deepdiff import DeepDiff
from langchain.chains.openai_functions import get_openai_output_parser
from langchain_core.runnables import (
    Runnable,
    RunnableLambda,
    RunnableParallel,
    RunnablePassthrough,
)
from langchain_core.runnables import (
    chain as chain_decorator,
)
from langchain_openai import ChatOpenAI

from compose2kube import llm, templates
from compose2kube.llm import Compose, Manifests, ManifestScore

N = 20
MODEL = llm.GPT35TURBO
logger = logging.getLogger(__name__)


# 0th layer
@chain_decorator
def canonicalize(path: str) -> str:
    newpath = Path(path).parent / "compose.config.yaml"
    return f"{newpath}"


@chain_decorator
def readtext(path: str) -> str:
    return Path(path).read_text()


# 1st layer
enrich_by_llm = llm.make_llm_runnable(tools=[Compose], model=MODEL, n=N)


def enrich_by_config(content: str) -> str:
    """TODO: 当面はあらかじめ変換し匿名加工済みのファイルを用いるため使用しない"""
    tmp = NamedTemporaryFile("w", prefix="composetmp", suffix=".yaml", delete=False)
    tmp.write(content)
    tmp.close()
    print(tmp.name)
    got = subprocess.check_output(
        f"docker compose -f {tmp.name} config", shell=True, universal_newlines=True
    )
    return got


# 2nd layer
@chain_decorator
def convert_by_kompose(content: str) -> Manifests | Exception:
    assert isinstance(content, str), type(content)
    tmp = NamedTemporaryFile("w", prefix="composetmp", suffix=".yaml", delete=False)
    tmp.write(content)
    tmp.close()
    print(tmp.name)
    cmd = f"kompose convert -f {tmp.name} --stdout --controller=Deployment --volumes persistentVolumeClaim --with-kompose-annotation=false"

    try:
        got = subprocess.check_output(cmd, shell=True, universal_newlines=True)
        return Manifests(manifests=[got])
    except subprocess.CalledProcessError as e:
        return e


convert_by_llm = llm.make_llm_runnable(tools=[Manifests], n=N, model=MODEL)

ops = RunnableParallel(
    #
    # method1
    canonical_kompose=canonicalize | readtext | convert_by_kompose | (lambda ms: [ms]),
    #
    # method2
    canonical_llm1_kompose=canonicalize
    | readtext
    | dict(
        input=lambda x: x,
        target=lambda _: "AWS EKS",
    )
    | templates.prompt1_for_kompose
    | enrich_by_llm  # Compose[]
    | (lambda xs: [x for x in xs if isinstance(x, Compose)])
    | (lambda cs: [c.spec for c in cast(list, cs)])  # Compose[] -> str[]
    | convert_by_kompose.map(),
    #
    # method3
    canonical_llm2=canonicalize
    | readtext
    | dict(
        input=lambda x: x,
        target=lambda _: "AWS EKS",
    )
    | templates.prompt_zeroshot
    | convert_by_llm,
    #
    # method4
    llm2=readtext
    | dict(
        input=lambda x: x,
        target=lambda _: "AWS EKS",
    )
    | templates.prompt_zeroshot
    | convert_by_llm,
)


@chain_decorator
def report(args: dict) -> dict:
    def compare(target: Manifests, human: Manifests) -> dict[str, int]:
        t1 = list(yaml.full_load_all(target.join()))
        t2 = list(yaml.full_load_all(human.join()))
        diff = DeepDiff(
            t1=t1,
            t2=t2,
            exclude_regex_paths=r".*metadata.*",
            ignore_order=True,
            get_deep_distance=True,
            cutoff_intersection_for_pairs=1,
            cutoff_distance_for_pairs=1,
        )
        return dict(deep_distance=diff.get("deep_distance", 0))

    answer: Manifests = args["answer"]
    generates = [m for m in args["generates"] if isinstance(m, Manifests)]
    generates_features = [m.feature() for m in generates]
    compares_to_answer = [compare(m, answer) for m in generates]

    return dict(
        **args,
        generates_features=generates_features,
        compares_to_answer=compares_to_answer,
    )


convert_chain = (
    # this chain accepts dict { input, answer }
    RunnablePassthrough.assign(
        answer=itemgetter("answer") | RunnableLambda(Manifests.from_file),
        manifests=itemgetter("input") | ops,  # key-value
    )
    | RunnableLambda(
        lambda dic: [
            {"input": dic["input"], "answer": dic["answer"], "op": k, "generates": v}  # type: ignore
            for k, v in dic["manifests"].items()  # type: ignore
        ]
    )
)


def dict_to_eval_prompt(dic: dict, n_samples: int) -> list[str]:
    compose_file = dic["input"]
    compose = Path(compose_file).read_text()
    gs = dic["generates"]
    gs: list[Manifests] = [g for g in gs if isinstance(g, Manifests)]
    specs: list[str] = [g.join() for g in gs][:n_samples]
    reference = f"""The manifest above is converted from the below compose file:

{compose}
"""

    return [
        templates.prompt_eval_manifests_create.format(manifest=s, reference=reference)
        for s in specs
    ]


eval_chain = RunnableParallel(
    inputs=RunnablePassthrough(),
    reports=report.with_fallbacks([RunnableLambda(lambda _: {})]),
    # llmeval=(
    #     RunnableLambda(
    #         lambda dic: dict_to_eval_prompt(dic, n_samples=5)
    #     )  # => list of prompts
    #     | ChatOpenAI(
    #         model=llm.GPT4TURBO,
    #         cache=True,
    #         temperature=0,
    #         model_kwargs={"seed": 1},
    #     )
    #     .bind_functions(functions=[ManifestScore])
    #     .map()
    #     # | get_openai_output_parser([ManifestScore]).map()
    # ),
)
