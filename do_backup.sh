#!/usr/bin/env bash
#   Name of backup user
BACKUP_USER="backup"
#   File with password for BACKUP_USER
BACKUP_PASSWORD_FILE="/etc/my.cnf.d/.pass"
#   Base folder for BACKUP
BACKUP_BASE_DIR="/data/backups"
#   Day of full backup in lowercase
# monday tuesday wednesday thursday friday saturday sunday
FULL_BACKUP_DAY=monday
FULL_BACKUP_COPY_NUM=4
FULL_BACKUP_PREFIX="backup_"
PARALLEL_THREAD_NUM=4
COMPRESS_THREAD_NUM=4
TODAY=`date +%F`

function extract_xtrabackup_logfile {
    echo "Try to decompress file xtrabackup_logfile.qp"
    if [[ -d $1 ]] ; then
        XTRABACKUP_LOGFILE=$1"/xtrabackup_logfile.qp"
        echo ${XTRABACKUP_LOGFILE}
        if [[ -f ${XTRABACKUP_LOGFILE} ]] ; then
            cmd="qpress -d $XTRABACKUP_LOGFILE $1"
            echo "Execute command $cmd to unpack xtrabackup_logfile file"
            ${cmd}
        else
            echo "Cant access to file $XTRABACKUP_LOGFILE"
        fi
    else
        echo "Cant access to folder $1"
    fi
}
function remove_old_backup {
    echo "Remove extra old backup, if needed"
    echo "Keep newes $FULL_BACKUP_COPY_NUM"
    let NUM=1+$FULL_BACKUP_COPY_NUM
    for i in `ls -l ${BACKUP_BASE_DIR} | grep ${FULL_BACKUP_PREFIX} | awk '{ print $9 }' | sort -r | tail -n +${NUM}` ; do
        DIR=${BACKUP_BASE_DIR}"/"${i}
        if [[ -d ${DIR} ]]; then
            echo "Remove old backup in folder $DIR"
            rm -rf ${DIR}
        fi
    done
}

function update_variables {
    YESTERDAY=`date -dyesterday +%F`
    FULL_BACKUP_DIR=${BACKUP_BASE_DIR}"/"${FULL_BACKUP_PREFIX}${DATE_OF_FULL_BACKUP}"/full"
    INC_BACKUP_DIR_TODAY=${BACKUP_BASE_DIR}"/"${FULL_BACKUP_PREFIX}${DATE_OF_FULL_BACKUP}"/inc_"${TODAY}
    INC_BACKUP_DIR_YESTERDAY=${BACKUP_BASE_DIR}"/"${FULL_BACKUP_PREFIX}${DATE_OF_FULL_BACKUP}"/inc_"${YESTERDAY}
}
function is_full_backup_today {
    #   If full backup exists return 1 (True)
    if [[ -f ${FULL_BACKUP_DIR}"/xtrabackup_logfile" ]]; then
        echo 1
    else
    #   If full backup not exits return 0 (False)
        echo 0
    fi
}
function get_day_of_today {
    echo $(to_lowercase `date +%A`)
}
function to_lowercase {
    echo $1 | tr '[:upper:]' '[:lower:]'
}
function mk_full_backup_dir {
    echo "Make full backup dir ${FULL_BACKUP_DIR}"
    mkdir -p ${FULL_BACKUP_DIR}
}
function mk_inc_backup_dir {
    if [ -d ${FULL_BACKUP_DIR} ]; then
        echo "Make incremental backup dir ${INC_BACKUP_DIR_TODAY}"
        mkdir -p ${INC_BACKUP_DIR_TODAY}
    else
        echo "Can't run incremental backup"
        echo "Can't find full backup directory (${FULL_BACKUP_DIR})"
        echo "or it's not presented in you system"
        echo "Exit..."
        exit 3
    fi
}

function make_backup_cmd_short {
local result="/usr/bin/xtrabackup -u ${BACKUP_USER} --password=`cat ${BACKUP_PASSWORD_FILE}` --compress --backup --no-lock --compress-threads=${COMPRESS_THREAD_NUM} --parallel=${PARALLEL_THREAD_NUM} --target-dir=${1}"
echo ${result}
}
function make_backup_cmd {
    #   First parameter target dir
    #   Second incremental base dir
    if [[ $2 ]]; then
        local result=$(make_backup_cmd_short ${1})" --incremental-basedir=${2}"
        echo ${result}
    else
        local result=$(make_backup_cmd_short ${1})
        echo ${result}
    fi
}

function backup_full {
    mk_full_backup_dir
    echo "Run full backup"
    cmd=$(make_backup_cmd ${FULL_BACKUP_DIR})
    echo ${cmd}
    ${cmd}
    extract_xtrabackup_logfile ${FULL_BACKUP_DIR}
    remove_old_backup
}

function backup_incremental {
    mk_inc_backup_dir
    echo "Run incremental backup"
    if [ -d ${INC_BACKUP_DIR_YESTERDAY} ]; then
        echo "Run incremental backup from incremental backup"
        cmd=$(make_backup_cmd ${INC_BACKUP_DIR_TODAY} ${INC_BACKUP_DIR_YESTERDAY})
        echo ${cmd}
        ${cmd}
        extract_xtrabackup_logfile
    else
        echo "Run incremental backup from full backup"
        cmd=$(make_backup_cmd ${INC_BACKUP_DIR_TODAY} ${FULL_BACKUP_DIR})
        echo ${cmd}
        ${cmd}
        extract_xtrabackup_logfile ${INC_BACKUP_DIR_TODAY}
    fi
}

if [[ ! -d $BACKUP_BASE_DIR ]] ; then
    echo "Can't find base backup directory $BACKUP_BASE_DIR"
    echo "Exit..."
    exit 2
fi

DAY_OF_TODAY=$(get_day_of_today)

echo "Run full backup every $FULL_BACKUP_DAY"
if [[ ${DAY_OF_TODAY} == ${FULL_BACKUP_DAY} ]] ; then
    echo "Today is day of full backup ($DAY_OF_TODAY, $TODAY)"
    DATE_OF_FULL_BACKUP=`date -d${FULL_BACKUP_DAY} +%F`
    update_variables
    if [[ $(is_full_backup_today) == 0 ]] ; then
        echo "Full backup was not created"
        echo "Run full backup"
        backup_full
    else
        echo "Full backup was created"
        echo "Run incremental backup"
        backup_incremental
    fi
elif [[ ${DAY_OF_TODAY} != ${FULL_BACKUP_DAY} ]] ; then
    echo "Today is not day of full backup ($DAY_OF_TODAY, $TODAY)"
    DATE_OF_FULL_BACKUP=`date -dlast-${FULL_BACKUP_DAY} +%F`
    update_variables
    if [[ $(is_full_backup_today) == 0 ]] ; then
        echo "Full backup was not created"
        echo "Run full backup"
        backup_full
    else
        echo "Full backup was created"
        echo "Run incremental backup"
        backup_incremental
    fi
else
    echo "Something new..."
    echo "Exit..."
    exit 1
fi