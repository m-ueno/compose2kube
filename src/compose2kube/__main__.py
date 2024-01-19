import os
from pathlib import Path
import glob
import argparse
import pickle
from logging import getLogger
import logging

from langfuse.callback import CallbackHandler
from langchain.globals import set_debug, set_verbose
from compose2kube import evaluator


def setup_logger(namespace: str, level: int):
    _root = getLogger(namespace)
    _root.setLevel(level)
    handler = logging.StreamHandler()
    handler.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    _root.addHandler(handler)


parser = argparse.ArgumentParser(prog="compose2kube")
parser.add_argument(
    "--convert",
    action="store_true",
    help="run convert compose.yaml to kube.yaml chain",
)
parser.add_argument("--eval", action="store_true", help="run evaluate chain")
parser.add_argument("--verbose", "-v", action="store_true")
parser.add_argument("--debug", action="store_true")
args = parser.parse_args()
if not (args.convert or args.eval):
    parser.print_help()
    exit(1)

PKGROOT = Path(os.path.dirname(os.path.abspath(__file__)))
INPUTROOTDIR = PKGROOT.parent.parent / "data" / "deployments_anonymized"
HUMANROOTDIR = PKGROOT.parent.parent / "data" / "manifest-by-human"
TMPFILE = "/tmp/got.pkl"
EVALFILE = "/tmp/eval.pkl"

loglevel = logging.ERROR
if args.verbose:
    loglevel = logging.INFO
elif args.debug:
    loglevel = logging.DEBUG

setup_logger("compose2kube", loglevel)
setup_logger(__name__, loglevel)
set_verbose(args.verbose)
set_debug(args.debug)
logger = getLogger(__name__)


def setup_langfuse():
    os.environ["LANGFUSE_HOST"] = "http://localhost:3000"
    os.environ["LANGFUSE_PUBLIC_KEY"] = "pk-lf-c551be63-507b-4edf-a561-1b2c9d112ee6"
    os.environ["LANGFUSE_SECRET_KEY"] = "sk-lf-f77580cc-1d37-41d1-b1e1-42b809b6b33b"
    handler = CallbackHandler()
    if not handler.auth_check():
        raise RuntimeError("langfuse auth failed")
    return handler


langfuse_handler = setup_langfuse()


def convert():
    inputfiles = glob.glob(f"{INPUTROOTDIR}/*/compose.yaml")
    answerfiles = glob.glob(f"{HUMANROOTDIR}/*/all.yaml")
    input = [{"input": k, "answer": v} for k, v in zip(inputfiles, answerfiles)]
    chain = evaluator.convert_chain

    got = chain.batch(input, config={"callbacks": [langfuse_handler]})

    with open(TMPFILE, "wb") as f:
        pickle.dump(got, f)

    print(f"wrote {TMPFILE}")
    return got


def evaluate():
    with open(TMPFILE, "rb") as f:
        got = pickle.load(f)

    # flatten
    items = sum(got, [])

    chain = evaluator.eval_chain
    got2 = chain.batch(items, config={"callbacks": [langfuse_handler]})
    with open(EVALFILE, "wb") as f:
        pickle.dump(got2, f)
    logger.info(f"wrote {EVALFILE}")


if args.convert:
    logger.info("start convert")
    convert()
if args.eval:
    logger.info("start eval")
    evaluate()
