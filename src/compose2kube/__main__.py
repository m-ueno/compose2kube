import os
from pathlib import Path
import glob
import argparse
import pickle

from langchain.globals import set_debug, set_verbose
from compose2kube import evaluator

parser = argparse.ArgumentParser(prog="compose2kube")
parser.add_argument("--verbose", "-v", action="store_true")
parser.add_argument("--debug", action="store_true")
args = parser.parse_args()

PKGROOT = Path(os.path.dirname(os.path.abspath(__file__)))
INPUTROOTDIR = PKGROOT.parent.parent / "data" / "deployments_anonymized"
HUMANROOTDIR = PKGROOT.parent.parent / "data" / "manifest-by-human"
TMPFILE = "/tmp/got.pkl"

set_verbose(args.verbose)
set_debug(args.debug)


def convert():
    inputfiles = glob.glob(f"{INPUTROOTDIR}/*/compose.yaml")
    answerfiles = glob.glob(f"{HUMANROOTDIR}/*/all.yaml")
    input = [{"input": k, "answer": v} for k, v in zip(inputfiles, answerfiles)]
    chain = evaluator.convert_chain

    got = chain.batch(input)

    with open(TMPFILE, "wb") as f:
        pickle.dump(got, f)

    print(f"wrote {TMPFILE}")
    return got


def evaluate():
    with open(TMPFILE, "rb") as f:
        got = pickle.load(f)

    chain = evaluator.eval_chain
    return chain.invoke(got)


convert()
