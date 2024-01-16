from pathlib import Path
import subprocess
from tempfile import NamedTemporaryFile
from typing import cast

from langchain_core.runnables import (
    Runnable,
    RunnableLambda,
    RunnablePassthrough,
    RunnableParallel,
    chain as chain_decorator,
)

from compose2kube import llm, templates
from compose2kube.llm import Compose, Manifests

N = 10
MODEL = llm.GPT35TURBO


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
    | convert_by_kompose.map(),  # ?
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


# eval chain
# {input, op, manifests}


def get_human_manifest(input):
    pass


def score(args: dict):
    args["input"]
    args["manifests"]


def compare(target: Manifests, human: Manifests):
    human.feature()
    pass


# whole chain

chain = (
    RunnableParallel(
        input=RunnablePassthrough(),
        manifests=RunnablePassthrough() | ops,  # key-value
    )
    | (
        lambda dic: [
            {"input": dic["input"], "op": k, "generates": v}
            for k, v in dic["manifests"].items()
        ]
    )  # list of dict {input, op, generates[]}
    | (lambda xs: xs)
)
