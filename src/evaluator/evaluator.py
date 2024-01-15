from dataclasses import dataclass
import enum
import pickle
from typing import Protocol
from collections import Counter, OrderedDict
from itertools import permutations, product
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Callable
from typing import Optional
import glob
import subprocess
import unittest
from tqdm import tqdm
import yaml

import pandas as pd
import glom

from notebooks.src.evaluator import llm
from notebooks.src.evaluator.llm import make_chain, make_chain_n

# model_name = "gpt-3.5-turbo-1106"
model_name = "gpt-4-1106-preview"
DEBUG = False

# 0th layer


def canonicalize(path: str) -> str:
    newpath = Path(path).parent / "compose.config.yaml"
    return f"{newpath}"


# 1st layer
def enrich_by_llm(content: str) -> str:
    chain = make_chain(
        prompt=llm.prompt1_for_kompose,
        model=model_name,
        seed=1,
        temperature=0,
        cache=True,
        tools=[llm.Compose],
    )
    callbacks = []
    got = chain.invoke(
        input=dict(input=content, target="EKS"),
        config={"callbacks": callbacks},
    )
    return got.spec


def enrich_by_config(content: str) -> str:
    tmp = NamedTemporaryFile("w", prefix="composetmp", suffix=".yaml", delete=False)
    tmp.write(content)
    tmp.close()
    print(tmp.name)
    got = subprocess.check_output(
        f"docker compose -f {tmp.name} config", shell=True, universal_newlines=True
    )
    return got


# 2nd layer
def convert_by_kompose(content: str) -> str:
    tmp = NamedTemporaryFile("w", prefix="composetmp", suffix=".yaml", delete=False)
    tmp.write(content)
    tmp.close()
    print(tmp.name)
    cmd = f"kompose convert -f {tmp.name} --stdout --controller=Deployment --volumes persistentVolumeClaim --with-kompose-annotation=false"
    return subprocess.check_output(cmd, shell=True, universal_newlines=True)


def convert_by_llm(content: str) -> list[str]:
    list_of_manifests = make_chain_n(
        template=llm.prompt_zeroshot,
        content=content,
        model=model_name,
        seed=1,
        tools=[llm.Manifests],
        n=10,
    )
    return [
        "---\n".join(m for m in manifests.manifests) for manifests in list_of_manifests
    ]


def readtext(path: str) -> str:
    return Path(path).read_text()


def applyfns(name: str, fns: list[Callable[[str], str]]) -> str:
    acc = name
    for fn in fns:
        try:
            acc = fn(acc)
        except Exception as e:
            print(e)
            raise e
            return ""
    return acc


def applyfns_list(input_file_path: str, fns) -> str | Exception | list[str | Exception]:
    acc = input_file_path

    def call_without_error(fn, arg) -> str | Exception:
        if isinstance(arg, Exception):
            return arg
        try:
            return fn(arg)
        except Exception as e:
            return e

    for fn in fns:
        if isinstance(acc, list):
            acc = [call_without_error(fn, x) for x in acc]
        else:
            acc = call_without_error(fn, acc)
    return acc


class TransformMethodName(enum.Enum):
    canonical_kompose = "0_canonical_kompose"
    canonical_llm1_kompose = "1_canonical_llm1_kompose"
    canonical_llm2 = "2_canonical_llm2"
    llm2 = "3_llm2"
    manual = "99_manual"


METHODS = OrderedDict(
    [
        (
            TransformMethodName.canonical_kompose,
            [
                canonicalize,
                readtext,
                convert_by_kompose,
            ],
        ),
        (
            TransformMethodName.canonical_llm1_kompose,
            [
                canonicalize,
                readtext,
                enrich_by_llm,
                convert_by_kompose,
            ],
        ),
        (
            TransformMethodName.canonical_llm2,
            [
                canonicalize,
                readtext,
                convert_by_llm,
            ],
        ),
        (
            TransformMethodName.llm2,
            [
                readtext,
                convert_by_llm,
            ],
        ),
    ]
)

#
# dataclasses for eval, not for openai
# [EvaluationEnvironment]
#   * outputdir
#   * datetime
#   * inputs
#   [ComposeFile] *--1 [ComposeFiles] 1--(op)--* [ManifestFile] 1--1 [ManifestEvaluation]
#
# 　((入力, 変換メソッド, 出力, 出力の枝番), 評価) の組を記録しあとで成形
#


# TODO: support multiple composefiles
@dataclass
class Composefile:
    path: Path

    @property
    def id(self):
        return self.path.parent.stem  # e.g. "automl"


@dataclass
class ManifestFile:
    path: Path

    input_ref: Composefile
    transform_method: TransformMethodName
    evaluation: Optional["ManifestEval"]

    @property
    def id(self):
        return self.path.stem

    def dry_run(self, server: bool) -> tuple[bool, str]:
        try:
            dryrun_opt = "client"
            if server:
                dryrun_opt = "server"
            cmd = f"microk8s.kubectl apply -f {self.path} --dry-run={dryrun_opt}"
            got = subprocess.check_output(
                cmd, shell=True, universal_newlines=True, stderr=subprocess.STDOUT
            )
            return True, got
        except subprocess.CalledProcessError as e:
            return False, e.output

    def feature(self) -> dict[str, int]:
        # マニフェストの「特徴量」を抽出する
        api_objects = list(yaml.safe_load_all(self.path.read_text()))
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


@dataclass
class ManifestEval:
    """Result represents a single conversion result.
    It contains dry-run result and comparison with human-written manifests.
    """

    dry_run: bool
    dry_run_msg: str
    diff: dict


@dataclass
class ManifestVariation:
    """ManifestVariation represents a single conversion result set."""

    manifestfiles: list[ManifestFile]
    input_ref: Composefile
    transform_method: TransformMethodName


NOTEBOOKDIR = Path(__file__).parent.parent.parent
ANSWER_DIR = NOTEBOOKDIR / "manifest-by-human"
DEPLOYMENT_DIR = NOTEBOOKDIR / "deployments_anonymized"


@dataclass
class MultiMethodEvaluator:
    inputs: list[Composefile]
    results: list[ManifestVariation]  # (input, op)の組が出力するnのマニフェストのリスト
    outputdir: Path

    def get_human_manifest(self, input: Composefile) -> ManifestFile:
        deployment_name = input.id
        return ManifestFile(
            path=Path(ANSWER_DIR) / deployment_name / "all.yaml",
            input_ref=input,
            transform_method=TransformMethodName.manual,
            evaluation=None,
        )

    def evaluate(self):
        """evaluate all inputs with all methods"""
        for input, method in tqdm(list(product(self.inputs, METHODS.keys()))):
            result = self.evaluate_one(input, method)
            self.results.append(result)

    def evaluate_one(
        self, input: Composefile, transform_method: TransformMethodName
    ) -> ManifestVariation:
        """evaluate one input with one method"""

        outputs = applyfns_list(input.path.__str__(), METHODS[transform_method])
        if not isinstance(outputs, list):
            outputs = [outputs]

        manifestfiles = []
        for i, text in enumerate(outputs):
            outputfile = (
                self.outputdir / f"{input.id}__{transform_method.value}_{i}.yaml"
            )
            outputfile.write_text(str(text))

            output = ManifestFile(
                path=outputfile,
                input_ref=input,
                transform_method=transform_method,
                evaluation=None,
            )

            # evaluate by dry-run
            dry_run_ok, dry_run_msg = output.dry_run(server=True)

            # evaluate by compare with human-written manifests
            human_manifest = self.get_human_manifest(input)
            feature = output.feature()
            feature_truth = human_manifest.feature()
            diff = {}
            keys = set(feature.keys()) | set(feature_truth.keys())
            for k in keys:
                if k is None:
                    continue
                diff[k] = glom.glom(feature, k, default=0) - glom.glom(
                    feature_truth, k, default=0
                )

            output.evaluation = ManifestEval(
                dry_run=dry_run_ok,
                dry_run_msg=dry_run_msg,
                diff=diff,
            )
            manifestfiles.append(output)
        return ManifestVariation(
            manifestfiles=manifestfiles,
            input_ref=input,
            transform_method=transform_method,
        )


class TestManifest(unittest.TestCase):
    def test_feature(self):
        content = """
apiVersion: v1
kind: Service
metadata:
    name: automl
spec:
    type: LoadBalancer
    ports:
    - port: 80
      targetPort: 80
    selector:
        app: automl
---
apiVersion: apps/v1
kind: Deployment
metadata:
    name: automl
spec:
    replicas: 1
    selector:
        matchLabels:
            app: automl
    template:
        metadata:
            labels:
                app: automl
        spec:
            containers:
            - name: automl
              image: automl
              ports:
              - containerPort: 80
              livenessProbe:
                  httpGet:
                      path: /healthz
                      port: 80
                  initialDelaySeconds: 30
                  periodSeconds: 30
                  timeoutSeconds: 5
                  failureThreshold: 3
"""
        tmpfile = NamedTemporaryFile("w", prefix="test_kube", suffix=".yaml")
        tmpfile.write(content)
        tmpfile.flush()
        got = ManifestFile(
            path=Path(tmpfile.name),
            input_ref=Composefile(path=Path("")),
            evaluation=None,
            transform_method=TransformMethodName.manual,
        ).feature()
        self.assertDictEqual(
            got,
            {
                "Service": 1,
                "Deployment": 1,
                "livenessProbe": 1,
                "readinessProbe": 0,
                "n_containers": 1,
            },
        )


class TestEvaluator(unittest.TestCase):
    def test_evaluate(self):
        inputs = [
            Composefile(path=Path(f))
            for f in glob.glob(f"{DEPLOYMENT_DIR}/*/compose.yaml")
        ]
        outputdir = Path("/tmp/output_20240112")
        outputdir.mkdir(exist_ok=True)

        evaluator = MultiMethodEvaluator(
            inputs=inputs,
            results=[],
            outputdir=outputdir,
        )
        evaluator.evaluate()
        print(evaluator.results)

        self.assertEqual(len(evaluator.results), 4 * 3)

    def test_applyfns_list(self):
        f = lambda x: x
        g = lambda x: list(range(x))
        f2 = lambda x: 1 / x
        tests = [
            (([f], 3), 3),
            (([f, f], 3), 3),
            (([f, g], 3), [0, 1, 2]),
            (([g], 3), [0, 1, 2]),
            (([g, f2], 3), [ZeroDivisionError("division by zero"), 1.0, 0.5]),
            (([g, f2, f2], 2), [ZeroDivisionError("division by zero"), 1.0]),
        ]
        for i, ((fns, arg), want) in enumerate(tests):
            with self.subTest(i=i):
                got = applyfns_list(arg, fns)
                self.assertEqual(pickle.dumps(got), pickle.dumps(want), got)
