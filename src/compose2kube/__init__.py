import logging

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())
