#!/usr/bin/env bash
#set -x
#set -e
### Configuration of backup script start
#   Name of backup user
BACKUP_USER="cumnsee_backup"
#   File with password for BACKUP_USER
BACKUP_PASSWORD_FILE="/etc/my.cnf.d/.pass"
#   Base folder for BACKUP
BACKUP_BASE_DIR="/mnt/blockstorage/backups"
#   Backup log file
BACKUP_LOG_FILE="/var/log/backup_log_`date +%F_%H-%M-%S`.log"
#   Day of the full backup, in lowercase
# monday tuesday wednesday thursday friday saturday sunday
FULL_BACKUP_DAY=monday
#   Number of saved full backups
FULL_BACKUP_COPY_NUM=4
#   Prefix for weekly backup folder
FULL_BACKUP_PREFIX="backup_"
#   Name of sub folder for full backup
FULL_BACKUP_FOLDER_NAME="full"
#   Prefix for sub folder with incremental backup
INCREMENTAL_FOLDER_NAME_PREFIX="inc_"
#   Number of threads for backup
PARALLEL_THREAD_NUM=4
#   Enable SELinux (Set 0 to disable)
ENABLE_SELINUX=0
#   Folder with mysql bin log files
MYSQL_BIN_LOG_PATH="/mnt/blockstorage/mysql-bin-log"
#   MySQL database folder
MYSQL_DB_PATH="/var/lib/mysql"
MYSQL_HOST="127.0.0.1"
MYSQL_PORT="3306"
MYSQL_USER="root"
### Configuration of backup script end

TODAY=`date +%F`
DATE_OF_FULL_BACKUP=""
DAMAGE_TIME=""

function get_damage_time () {
    echo "Enter time when you database was damaged (in format like 2018-07-15T19:27:00)"
    local TIME
    read TIME
    DAMAGE_TIME=${TIME}
}
function to_lowercase {
    echo $1 | tr '[:upper:]' '[:lower:]'
}
function get_day_of_today () {
    echo $(to_lowercase `date +%A`)
}
DAY_OF_TODAY=$(get_day_of_today)
if [[ ${DAY_OF_TODAY} == ${FULL_BACKUP_DAY} ]] ; then
    echo "`date +%F_%T` Today is day of full backup ($DAY_OF_TODAY, $TODAY)"
    DATE_OF_FULL_BACKUP=`date -d${FULL_BACKUP_DAY} +%F`
else
    echo "`date +%F_%T` Today is not day of full backup ($DAY_OF_TODAY, $TODAY)"
    DATE_OF_FULL_BACKUP=`date -dlast-${FULL_BACKUP_DAY} +%F`
fi
FULL_BACKUP_DIR=${BACKUP_BASE_DIR}"/"${FULL_BACKUP_PREFIX}${DATE_OF_FULL_BACKUP}"/"${FULL_BACKUP_FOLDER_NAME}
BACKUP_PATH_FILE="/tmp/backup_path"
LAST_INCREMENTAL_BACKUP_FOLDER_FILE="/tmp/last_incremental_backup_folder"
BIN_LOG_IN_SQL="/tmp/converted_mysql_bin_logs_`date +%F_%H-%M-%S`.sql"

function apply_folder_permissions () {
    echo "`date +%F_%T` Set folder permissions"
    chown mysql:mysql ${MYSQL_DB_PATH} -R
    chmod 775 ${MYSQL_DB_PATH} -R
    if [[ ${ENABLE_SELINUX} == 1 ]] ; then
        semanage fcontext -a -t mysqld_db_t "${MYSQL_DB_PATH}(/.*)?"
        restorecon -vrF ${MYSQL_DB_PATH}
    fi
}

function make_binlog_info_file_path () {
    echo $1"/xtrabackup_binlog_info"
}
function get_binlog_info_file () {
    if [[ -f ${LAST_INCREMENTAL_BACKUP_FOLDER_FILE} ]] ; then
        local INC_DIR=$(cat ${LAST_INCREMENTAL_BACKUP_FOLDER_FILE})
        local INC_FILE=$(make_binlog_info_file_path ${INC_DIR})
        if [[ -f ${INC_FILE} ]] ; then
            echo ${INC_FILE}
        else
            echo "Can't find xtrabackup_binlog_info file in ${INC_DIR}"
        fi
    elif [[ -f ${BACKUP_PATH_FILE} ]] ; then
        local INC_DIR=$(cat ${LAST_INCREMENTAL_BACKUP_FOLDER_FILE})
        local INC_FILE=$(make_binlog_info_file_path ${INC_DIR})
        if [[ -f ${INC_FILE} ]] ; then
            echo ${INC_FILE}
        else
            echo "Can't find xtrabackup_binlog_info file in ${INC_DIR}"
        fi
    else
        echo "Can't find folder with incremental or full backup"
        exit 13
    fi
}

function convert_bin_log_to_sql () {
    echo "`date +%F_%T` Converting MySQL binary logs to SQL"
    local BINLOG_INFO_FILE=$(get_binlog_info_file)
    local STORED_BIN_FILE_SHORT=$(cat ${BINLOG_INFO_FILE} | awk ' { print $1 } ')
    local STORED_BIN_FILE_POSITION=$(cat ${BINLOG_INFO_FILE} | awk ' { print $2 } ')
    local BIN_FILES=($(ls -l ${MYSQL_BIN_LOG_PATH} | grep -v 'index' | awk ' { print $9 }' | grep ${STORED_BIN_FILE_SHORT} -A9999999999))
    local BIN_FILES_LINE=""
    for i in ${BIN_FILES[@]} ;
    do
        local BIN_FILE=${MYSQL_BIN_LOG_PATH}"/"${i}
        BIN_FILES_LINE=${BIN_FILES_LINE}" "${BIN_FILE}
    done
    local cmd=""
    if [[ ${DAMAGE_TIME} == "" ]] ; then
        cmd="mysqlbinlog --start-position=${STORED_BIN_FILE_POSITION} ${BIN_FILES_LINE}"
    else
        cmd="mysqlbinlog --start-position=${STORED_BIN_FILE_POSITION} --stop-datetime=${DAMAGE_TIME} ${BIN_FILES_LINE}"
    fi
    echo "Convert MySQL bin logs with command ${cmd}"
    ${cmd} > ${BIN_LOG_IN_SQL}
}


function apply_converted_bin_log () {
    echo "`date +%F_%T` Apply converted binary logs to DB"
    echo "Enter password for user ${MYSQL_USER} at host ${MYSQL_HOST}:${MYSQL_PORT}"
    mysql -u ${MYSQL_USER} -P ${MYSQL_PORT} -h ${MYSQL_HOST} -p < ${BIN_LOG_IN_SQL}
}

function apply_bin_log () {
    convert_bin_log_to_sql
    apply_converted_bin_log
    echo "Done"
}

function prepare_full_backup {
    if [[ $1 ]] ; then
        echo -e "`date +%F_%T` Prepare full backup to restore"
        local FULL_BACKUP=$1"/"${FULL_BACKUP_FOLDER_NAME}
        echo ${FULL_BACKUP} > ${BACKUP_PATH_FILE}
        if [[ -d ${FULL_BACKUP} ]] ; then
            echo "`date +%F_%T` Full backup stored in folder $FULL_BACKUP"
            local cmd="xtrabackup --prepare --apply-log-only --target-dir=${FULL_BACKUP}"
            echo "`date +%F_%T` Run command $cmd to prepare full backup"
            ${cmd} >> ${BACKUP_LOG_FILE}
        else
            echo "`date +%F_%T` Can't find full backup"
            exit 8
        fi
    else
        echo "`date +%F_%T` Full backup folder is not presented"
        exit 7
    fi
}

function prepare_incremental_backup () {
    local BACKUP_FULL=$1
    local BACKUP_INCREMENTAL=$2
    if [[ (-d ${BACKUP_FULL}) && (-d ${BACKUP_INCREMENTAL}) ]] ; then
        echo "`date +%F_%T` Merge incremental backup with full backup"
        echo "`date +%F_%T` Full backup - $BACKUP_FULL"
        echo "`date +%F_%T` Incremental backup - $BACKUP_INCREMENTAL"
        cmd="xtrabackup --prepare --apply-log-only --target-dir=$BACKUP_FULL --incremental-dir=$BACKUP_INCREMENTAL"
        echo ${cmd}
        ${cmd}
    else
        echo "`date +%F_%T` Missing folder with full or incremental backup"
        exit 11
    fi
}
function prepare_last_incremental_backup () {
    local BACKUP_FULL=$1
    local BACKUP_INCREMENTAL=$2
    if [[ (-d ${BACKUP_FULL}) && (-d ${BACKUP_INCREMENTAL}) ]] ; then
        echo "`date +%F_%T` Merge last incremental backup with full backup"
        echo "`date +%F_%T` Full backup - $BACKUP_FULL"
        echo "`date +%F_%T` Last incremental backup - $BACKUP_INCREMENTAL"
        echo ${BACKUP_INCREMENTAL} > ${LAST_INCREMENTAL_BACKUP_FOLDER_FILE}
        cmd="xtrabackup --prepare --target-dir=$BACKUP_FULL --incremental-dir=$BACKUP_INCREMENTAL"
        echo ${cmd}
        ${cmd}
    else
        echo "`date +%F_%T` Missing folder with full or last incremental backup"
        exit 10
    fi
}
function prepare_incremental_backups() {
    if [[ $1 ]] ; then
        echo "`date +%F_%T` Prepare incremental backups to restore"
        local BACKUP_DIR=$1
        local FULL_BACKUP=${BACKUP_DIR}"/"${FULL_BACKUP_FOLDER_NAME}
        INCREMENTAL_BACKUPS=($(ls -l ${BACKUP_DIR} | grep ${INCREMENTAL_FOLDER_NAME_PREFIX} | awk ' { print $9 } '))
        INCREMENT_NUM=${#INCREMENTAL_BACKUPS[@]}
        if [[ ${INCREMENT_NUM} == 0 ]] ; then
            echo "`date +%F_%T` No incremental backups, move on"
        elif [[ ${INCREMENT_NUM} == 1 ]]; then
            echo "`date +%F_%T` Only one incremental backup"
            local INCREMENTAL_BACKUP=${BACKUP_DIR}"/"${INCREMENTAL_BACKUPS[0]}
            prepare_last_incremental_backup ${FULL_BACKUP} ${INCREMENTAL_BACKUP}
        elif [[ ${INCREMENT_NUM} > 1 ]] ; then
            echo "`date +%F_%T` There are $INCREMENT_NUM incremental backups"
            FIRST_INCREMENTAL_BACKUPS=(${INCREMENTAL_BACKUPS[@]::${#INCREMENTAL_BACKUPS[@]}-1})
            LAST_INCREMENTAL_BACKUP="${INCREMENTAL_BACKUPS[-1]}"
            for i in ${FIRST_INCREMENTAL_BACKUPS[@]} ;
            do
                local INCREMENTAL_BACKUP=${BACKUP_DIR}"/"${i}
                prepare_incremental_backup ${BACKUP_DIR} ${INCREMENTAL_BACKUP}
            done
            local INCREMENTAL_BACKUP=${BACKUP_DIR}"/"${INCREMENTAL_BACKUPS[0]}
            prepare_last_incremental_backup ${FULL_BACKUP} ${INCREMENTAL_BACKUP}
        else
            echo "`date +%F_%T` Number of incremental backup not less 0"
            exit 9
        fi
    else
        echo "`date +%F_%T` Incremental backup folder is not presented"
        exit 9
    fi
}

function containsElement () {
  local e match="$1"
  shift
  for e; do [[ "$e" == "$match" ]] && echo 0; done
  echo 1
}

function select_backup () {
    local BACKUP_LIST=$(ls -l ${BACKUP_BASE_DIR} | grep ${FULL_BACKUP_PREFIX} | awk ' { print $9 } ')
    echo "`date +%F_%T` List of available backups in folder ${BACKUP_BASE_DIR}:"
    printf '%s\n' "${BACKUP_LIST[@]}"
    echo "`date +%F_%T` Enter name of weekly backup and press ENTER:"
    read BACKUP
    local r=$(containsElement ${BACKUP} ${BACKUP_LIST[@]})
    if [[ ${r}  == 1 ]] ; then
        echo "`date +%F_%T` Chosen backup not available in backup list"
        exit 5
    fi
    echo "`date +%F_%T` You choose backup ${BACKUP} from folder ${BACKUP_BASE_DIR}"
    echo -n "Are you sure in your choose? [Y(yes) or N(no)]: "
    read sure
    if [[ $(to_lowercase $sure) == "y" ]] ; then
        echo "`date +%F_%T` Start preparation before restoration"
        echo ${BACKUP_BASE_DIR}"/"${BACKUP} > ${BACKUP_PATH_FILE}
    else
        echo "`date +%F_%T` You not sure - exit"
        exit 6
    fi
}

function prepare_backups {
    if [[ ! -d ${MYSQL_DB_PATH} ]]; then
        echo "`date +%F_%T` Prepare backups to restore"
        select_backup
        local BACKUP_PATH=$(cat ${BACKUP_PATH_FILE})
        echo "`date +%F_%T` Folder with backup - ${BACKUP_PATH}"
        prepare_full_backup ${BACKUP_PATH}
        prepare_incremental_backups ${BACKUP_PATH}
    else
        echo "`date +%F_%T` Can't restore because folder ${MYSQL_DB_PATH} already exists!"
        echo "`date +%F_%T` Move it to other location before restoration"
        exit 4
    fi
}

function extract_xtrabackup_files {
    extract_xtrabackup_logfile $1
    extract_xtrabackup_binlog_info $1
}


function remove_old_backup {
    echo "`date +%F_%T` Remove extra old backup, if needed" >> ${BACKUP_LOG_FILE} 2>&1
    echo "`date +%F_%T` Number of newest backup for saving - $FULL_BACKUP_COPY_NUM" >> ${BACKUP_LOG_FILE} 2>&1
    let NUM=1+$FULL_BACKUP_COPY_NUM
    for i in `ls -l ${BACKUP_BASE_DIR} | grep ${FULL_BACKUP_PREFIX} | awk '{ print $9 }' | sort -r | tail -n +${NUM}` ; do
        DIR=${BACKUP_BASE_DIR}"/"${i}
        if [[ -d ${DIR} ]]; then
            echo "`date +%F_%T` Remove old backup in folder $DIR" >> ${BACKUP_LOG_FILE} 2>&1
            rm -rf ${DIR}
        fi
    done
}

function update_variables {
    YESTERDAY=`date -dyesterday +%F`
    BACKUP_DIR=${BACKUP_BASE_DIR}"/"${FULL_BACKUP_PREFIX}${DATE_OF_FULL_BACKUP}"/"${FULL_BACKUP_FOLDER_NAME}
    INC_BACKUP_DIR_TODAY=${BACKUP_BASE_DIR}"/"${FULL_BACKUP_PREFIX}${DATE_OF_FULL_BACKUP}"/"${INCREMENTAL_FOLDER_NAME_PREFIX}${TODAY}
    INC_BACKUP_DIR_YESTERDAY=${BACKUP_BASE_DIR}"/"${FULL_BACKUP_PREFIX}${DATE_OF_FULL_BACKUP}"/"${INCREMENTAL_FOLDER_NAME_PREFIX}${YESTERDAY}
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
function mk_full_backup_dir {
    if [[ ${FULL_BACKUP_DIR} ]] ; then
        echo "`date +%F_%T` Make full backup dir ${FULL_BACKUP_DIR}" >> ${BACKUP_LOG_FILE} 2>&1
        mkdir -p ${FULL_BACKUP_DIR}
    else
        exit 99
    fi
}
function mk_inc_backup_dir {
    if [ -d ${FULL_BACKUP_DIR} ]; then
        echo "`date +%F_%T` Make incremental backup dir ${INC_BACKUP_DIR_TODAY}" >> ${BACKUP_LOG_FILE} 2>&1
        mkdir -p ${INC_BACKUP_DIR_TODAY}
    else
        echo "`date +%F_%T` Can't run incremental backup"
        echo "`date +%F_%T` Can't find full backup directory (${FULL_BACKUP_DIR})"
        echo "`date +%F_%T` or it's not presented in you system"
        echo "`date +%F_%T` Exit..."
        exit 3
    fi
}

function make_backup_cmd_short {
local result="/usr/bin/xtrabackup -u ${BACKUP_USER} --password=`cat ${BACKUP_PASSWORD_FILE}` --backup --no-lock --parallel=${PARALLEL_THREAD_NUM} --target-dir=${1}"
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
    echo "`date +%F_%T` Run full backup" >> ${BACKUP_LOG_FILE} 2>&1
    local cmd=$(make_backup_cmd ${FULL_BACKUP_DIR})
    ${cmd} >> ${BACKUP_LOG_FILE} 2>&1
    # extract_xtrabackup_files ${FULL_BACKUP_DIR}
}

function backup_incremental {
    mk_inc_backup_dir
    echo "`date +%F_%T` Run incremental backup" >> ${BACKUP_LOG_FILE} 2>&1
    if [ -d ${INC_BACKUP_DIR_YESTERDAY} ]; then
        echo "`date +%F_%T` Run incremental backup from incremental backup" >> ${BACKUP_LOG_FILE} 2>&1
        cmd=$(make_backup_cmd ${INC_BACKUP_DIR_TODAY} ${INC_BACKUP_DIR_YESTERDAY})
        ${cmd} >> ${BACKUP_LOG_FILE} 2>&1
#        extract_xtrabackup_files ${INC_BACKUP_DIR_TODAY}
    else
        echo "`date +%F_%T` Run incremental backup from full backup" >> ${BACKUP_LOG_FILE} 2>&1
        cmd=$(make_backup_cmd ${INC_BACKUP_DIR_TODAY} ${FULL_BACKUP_DIR})
        ${cmd} >> ${BACKUP_LOG_FILE} 2>&1
#        extract_xtrabackup_files ${INC_BACKUP_DIR_TODAY}
    fi
}

function restore_db {
    local FULL_BACKUP=$(cat ${BACKUP_PATH_FILE})
    echo ${FULL_BACKUP}
    if [[ ${FULL_BACKUP} ]] ; then
        echo "`date +%F_%T` Start restoration of databases"
        if [[ -d ${FULL_BACKUP} ]] ; then
            echo "`date +%F_%T` Start restore databases"
            local cmd="xtrabackup --copy-back --target-dir=${FULL_BACKUP}"
            echo "`date +%F_%T` Execute restoring database with command ${cmd}"
            ${cmd}
        else
            echo "`date +%F_%T` Folder with full backup not found"
            exit 13
        fi
    else
        echo "`date +%F_%T` Missing folder with full prepared backup"
        exit 12
    fi
}

function start_mysql() {
    echo "`date +%F_%T` Trying to start MySQL"
    systemctl start mysql
}
function restore () {
    echo "`date +%F_%T` Prepare backup and restore it"
    prepare_backups
    restore_db
    apply_folder_permissions
    start_mysql
    echo -n "Do you want apply MySQL binary logs? [Y(yes) or N(no)]: "
    read sure
    if [[ $(to_lowercase ${sure}) == "y" ]] ; then
        get_damage_time
        echo "Damage time - ${DAMAGE_TIME}"
        apply_bin_log
    else
        echo "`date +%F_%T` You not sure - exit"
        exit 6
    fi
}
function make_backup {
    local DAY_OF_TODAY=$(get_day_of_today)
    echo "`date +%F_%T` Run full backup every $FULL_BACKUP_DAY" >> ${BACKUP_LOG_FILE} 2>&1
    if [[ ${DAY_OF_TODAY} == ${FULL_BACKUP_DAY} ]] ; then
        echo "`date +%F_%T` Today is day of full backup ($DAY_OF_TODAY, $TODAY)" >> ${BACKUP_LOG_FILE} 2>&1
        DATE_OF_FULL_BACKUP=`date -d${FULL_BACKUP_DAY} +%F`
        update_variables
        if [[ $(is_full_backup_today) == 0 ]] ; then
            echo "`date +%F_%T` Full backup was not created" >> ${BACKUP_LOG_FILE} 2>&1
            echo "`date +%F_%T` Run full backup" >> ${BACKUP_LOG_FILE} 2>&1
            backup_full
            backup_incremental
        else
            echo "`date +%F_%T` Full backup was created" >> ${BACKUP_LOG_FILE} 2>&1
            echo "`date +%F_%T` Run incremental backup" >> ${BACKUP_LOG_FILE} 2>&1
            backup_incremental
        fi
    elif [[ ${DAY_OF_TODAY} != ${FULL_BACKUP_DAY} ]] ; then
        echo "`date +%F_%T` Today is not day of full backup ($DAY_OF_TODAY, $TODAY)" >> ${BACKUP_LOG_FILE} 2>&1
        DATE_OF_FULL_BACKUP=`date -dlast-${FULL_BACKUP_DAY} +%F`
        update_variables
        if [[ $(is_full_backup_today) == 0 ]] ; then
            echo "`date +%F_%T` Full backup was not created" >> ${BACKUP_LOG_FILE} 2>&1
            echo "`date +%F_%T` Run full backup" >> ${BACKUP_LOG_FILE} 2>&1
            backup_full
            backup_incremental
        else
            echo "`date +%F_%T` Full backup was created" >> ${BACKUP_LOG_FILE} 2>&1
            echo "`date +%F_%T` Run incremental backup" >> ${BACKUP_LOG_FILE} 2>&1
            backup_incremental
        fi
    else
        echo "`date +%F_%T` Something new..."
        echo "`date +%F_%T` Exit..."
        exit 1
    fi
    remove_old_backup
}
if [[ ! -d ${BACKUP_BASE_DIR} ]] ; then
    echo "`date +%F_%T` Can't find base backup directory $BACKUP_BASE_DIR"
    echo "`date +%F_%T` Exit..."
    exit 2
fi

if [[ $1 == "restore" ]] ; then
    restore
elif [[ $1 == "backup" ]] ; then
    make_backup
else
    echo "For backup run with key backup"
    echo "example - ./do_backup.sh backup"
    echo "For restore run with key restore"
    echo "example - ./do_backup.sh restore"
fi