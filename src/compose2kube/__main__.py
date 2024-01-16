import os
from pathlib import Path
import glob
import argparse

from langchain.globals import set_debug, set_verbose

from compose2kube import evaluator


parser = argparse.ArgumentParser(prog="compose2kube")
parser.add_argument("--verbose", "-v", action="store_true")
parser.add_argument("--debug", action="store_true")
args = parser.parse_args()

PKGROOT = Path(os.path.dirname(os.path.abspath(__file__)))
INPUTROOTDIR = PKGROOT.parent.parent / "data" / "deployments_anonymized"
HUMANROOTDIR = PKGROOT.parent.parent / "data" / "manifest-by-human"

set_verbose(args.verbose)
set_debug(args.debug)


def evaluate():
    inputfiles = glob.glob(f"{INPUTROOTDIR}/*/compose.yaml")
    chain = evaluator.chain
    return chain.batch(inputfiles)


got = evaluate()
print(got)
