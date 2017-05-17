#!/bin/sh

THIS_SCRIPT=$0
THIS_DIR=$(dirname $0)

. ${THIS_DIR}/settings.sh

exec ${THIS_DIR}/currentcost.py --fake
