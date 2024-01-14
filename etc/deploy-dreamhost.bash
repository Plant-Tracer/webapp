#!/bin/bash
#
# deploy-dreamhost [user@host] [dir] [branch]
#
# Designed to be run from the developer's system or GitHub Actions.
# Deploys to dreamhost
SCRIPT=$(realpath "$0")
SCRIPTPATH=$(dirname "$SCRIPT")
ROOT=$(dirname "$SCRIPTPATH")
REPO=https://github.com/Plant-Tracer/webapp.git

if [[ $# -ne 3  ]] ; then
   echo usage: $SCRIPT '[host] [branch]'
   exit 1
fi

host=$1
dir=$2
branch=$3
credentials=etc/credentials.ini

ssh $1 "echo hostname=\$(hostname) pwd=\$(pwd) \
    && dir=$dir \
    && new=$dir.\$\$ \
    && old=$dir.\$(date +'%s') \
    && if [[ ! -x $dir ]]; then echo \$(hostname): \$(pwd)/$dir/ does not exist ; exit 1 ; fi \
    && /bin/rm -rf \$new \
    && git clone -b $branch --recurse-submodules $REPO \$new \
    && cp \$dir/$credentials \$new/$credentials \
    && cd \$new \
    && make install-ubuntu \
    && make pytest-quiet \
    && cd .. \
    && zip \$old.zip -r \$dir \
    && mv \$dir \$old \
    && mv \$new \$dir \
    && /bin/rm -rf \$old \
    && cat error.log >> error.log.old \
    && truncate error.log --size 0 \
    && echo \$dir: \
    && ls -l \$dir \
    && echo \$(pwd): \
    && ls -l "
