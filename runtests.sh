#!/bin/bash

set -xe

make install

cd tests/

ansible-playbook -i localhost playbook.yml

for MODULE in /var/lib/breakoscope/*; do
    if [[ -d $MODULE ]]; then
	echo Testing ${MODULE##*/}
	if [[ ${MODULE##*/} != postgres ]]; then
   	    RESULT=$(breakoscope ${MODULE##*/})
	else
   	    RESULT=$(sudo -u postgres breakoscope ${MODULE##*/})
        fi
	CMP=$(echo -ne "$RESULT" | python3 -c 'import json, sys ; print(set(json.load(sys.stdin)["config_files"]) == set(json.load(open("'results/${MODULE##*/}.json'"))["config_files"]))')
	if [[ $CMP != True ]]; then
            cat results/${MODULE##*/}.json
	    exit 1
	fi
    fi
done
