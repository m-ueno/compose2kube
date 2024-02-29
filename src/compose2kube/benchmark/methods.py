import subprocess
import tempfile
from logging import getLogger

from langchain.prompts import PromptTemplate
from langchain_core.documents import Document
from langchain_core.runnables import (
    ConfigurableField,
    RunnableLambda,
    RunnablePassthrough,
)
from langchain_core.runnables import (
    chain as chain_decorator,
)

from compose2kube import templates
from compose2kube.benchmark.parser import MDCodeBlockOutputParser
from compose2kube.model import ChatOpenAIMultiGenerations

logger = getLogger(__name__)


@chain_decorator
def canonicalize(spec: Document) -> Document:
    """return stdout and stderr separately of command `docker compose config`"""
    with tempfile.NamedTemporaryFile(
        "w", prefix="canonicalize", suffix=".yaml", delete=False
    ) as tmp:
        tmp.write(spec.page_content)
        tmp.close()
        logger.debug(tmp.name)

        # get stdout and stderr separately using pipe
        with subprocess.Popen(
            f"docker compose -f {tmp.name} config --no-path-resolution --no-interpolate",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
        ) as proc:
            stdout, stderr = proc.communicate()
            return Document(page_content=stdout, metadata=dict(stderr=stderr))


@chain_decorator
def kompose(spec: Document) -> Document:
    """return output of command `kompose convert`"""
    with tempfile.NamedTemporaryFile(
        "w", prefix="kompose", suffix=".yaml", delete=False
    ) as tmp:
        tmp.write(spec.page_content)
        tmp.close()
        logger.debug(tmp.name)

        with subprocess.Popen(
            f"kompose convert -f {tmp.name} --stdout",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
        ) as proc:
            stdout, stderr = proc.communicate()
            return Document(page_content=stdout, metadata=dict(stderr=stderr))


chain_annotate_kompose = (
    {"input": lambda doc: doc.page_content, "target": lambda _: "AWS EKS"}
    | templates.prompt1_for_kompose
    | ChatOpenAIMultiGenerations(
        cache=True, model_kwargs={"seed": 1}
    ).configurable_fields(
        n=ConfigurableField(id="n"), model_name=ConfigurableField(id="model_name")
    )
    | (MDCodeBlockOutputParser() | kompose).map()
)

chain_canonical_annotate_kompose = canonicalize | chain_annotate_kompose


@chain_decorator
def to_doc(page_content: str, **kwargs) -> Document:
    return Document(page_content=page_content, **kwargs)


#
# 前処理なし
#
prompt_zeroshot = PromptTemplate.from_template(
    "convert the composefile to kubernetes manifests:\n{compose}"
)

chain_zeroshottext = (
    {"compose": lambda doc: doc.page_content}
    | prompt_zeroshot
    | ChatOpenAIMultiGenerations(
        cache=True, model_kwargs={"seed": 1}
    ).configurable_fields(
        n=ConfigurableField(id="n"), model_name=ConfigurableField(id="model_name")
    )
    | (MDCodeBlockOutputParser() | to_doc).map()
)

#
# input is a Document, output is a List[Document]
CONVERT_METHODS = dict(
    annotate_kompose=chain_annotate_kompose,
    canonical_annotate_kompose=chain_canonical_annotate_kompose,
    zeroshottext=chain_zeroshottext,
)
