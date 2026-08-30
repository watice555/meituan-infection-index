#!/bin/zsh

set -u

backup_dir="${0:A:h}"
project_dir="${backup_dir:h}"
log_dir="${backup_dir}/data/logs"

mkdir -p "${log_dir}"
cd "${project_dir}" || exit 1

started_at="$(date '+%Y-%m-%d %H:%M:%S %Z')"
printf '[%s] Starting local Meituan index backup\n' "${started_at}" >> "${log_dir}/backup.log"

if /usr/bin/python3 "${backup_dir}/backup.py" >> "${log_dir}/backup.log" 2>> "${log_dir}/backup.error.log"; then
    exit_code=0
else
    exit_code=$?
fi

finished_at="$(date '+%Y-%m-%d %H:%M:%S %Z')"
printf '[%s] Finished with exit code %s\n' "${finished_at}" "${exit_code}" >> "${log_dir}/backup.log"
exit "${exit_code}"
