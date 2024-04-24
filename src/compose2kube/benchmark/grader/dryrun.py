import subprocess
import tempfile

from langchain_core.runnables import chain as chain_decorator

from .judgement import Judgement


@chain_decorator
def dryrun_str(manifests: str) -> Judgement:
    """execute kubectl apply --dry-run=server"""

    # generate tmpfile
    with tempfile.NamedTemporaryFile(
        "w", prefix="dryrun", suffix=".yaml", delete=False
    ) as f:
        f.write(manifests)
        f.close()
        # get stdout and stderr separately using pipe
        with subprocess.Popen(
            f"kubectl apply -f {f.name} --dry-run=server",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
        ) as proc:
            stdout, stderr = proc.communicate()
            return Judgement(
                ok=proc.returncode == 0, metadata=dict(stdout=stdout, stderr=stderr)
            )
