#!/bin/bash -xeu

# See commands at https://hub.docker.com/r/apache/superset
superset fab create-admin --username admin --firstname Superset --lastname Admin --email admin@superset.com --password admin
superset db upgrade
# superset load_examples
superset init

/usr/bin/run-server.sh
