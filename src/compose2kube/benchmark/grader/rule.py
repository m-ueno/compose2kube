import re

import yaml

from compose2kube.benchmark.dataset import input3, input4, input5, input12
from .judgement import Judgement

input9 = input4


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
