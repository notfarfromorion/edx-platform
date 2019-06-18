#!/bin/bash
set -e

echo "Spinning up xdist workers with pytest_worker_manager.py"
python scripts/xdist/pytest_worker_manager.py -a up -n ${XDIST_NUM_WORKERS} \
-ami ${XDIST_WORKER_AMI} \
-type ${XDIST_INSTANCE_TYPE} \
-s ${XDIST_WORKER_SUBNET} \
-sg ${XDIST_WORKER_SECURITY_GROUP} \
-key ${XDIST_WORKER_KEY_NAME} \
-iam ${XDIST_WORKER_IAM_PROFILE_ARN}

# Need to map remote branch to local branch when fetching a branch other than master
if [ "$XDIST_GIT_BRANCH" == "master" ]; then
    XDIST_GIT_FETCH_STRING="$XDIST_GIT_BRANCH"
else
    XDIST_GIT_FETCH_STRING="$XDIST_GIT_BRANCH:$XDIST_GIT_BRANCH"
fi

# Install the correct version of Django depending on which tox environment (if any) is in use
if [[ -z ${TOX_ENV+x} ]] || [[ ${TOX_ENV} == 'null' ]]; then
    DJANGO_REQUIREMENT="-r requirements/edx/django.txt"
else
    DJANGO_REQUIREMENT=$(pip freeze | grep "^[Dd]jango==")
fi

ip_list=$(<pytest_worker_ips.txt)
for ip in $(echo $ip_list | sed "s/,/ /g")
do
    worker_reqs_cmd="ssh -o StrictHostKeyChecking=no ubuntu@$ip 'cd /edx/app/edxapp;
    git clone --branch master --depth 1 --no-tags -q https://github.com/edx/edx-platform.git; cd edx-platform;
    git fetch --depth=1 --no-tags -q origin ${XDIST_GIT_FETCH_STRING}; git checkout -q ${XDIST_GIT_BRANCH};
    source /edx/app/edxapp/edxapp_env;
    pip install -q ${DJANGO_REQUIREMENT} -r requirements/edx/testing.txt; mkdir reports' & "

    cmd=$cmd$worker_reqs_cmd
done
cmd=$cmd"wait"

echo "Executing commmand: $cmd"
eval $cmd
