import argparse
import logging
import subprocess
from datetime import datetime, timedelta
#   Name of backup user
from typing import List

BACKUP_USER = "cumnsee_backup"
#   File with password for BACKUP_USER
BACKUP_PASSWORD_FILE = "/etc/my.cnf.d/.pass"
#   Base folder for BACKUP
BACKUP_BASE_DIR = "/mnt/blockstorage/backups"
#   Number of day for full backup
# monday tuesday wednesday thursday friday saturday sunday
#   1      2         3        4       5       6       7
FULL_BACKUP_DAY = 1
#   Number of saved full backups
FULL_BACKUP_COPY_NUM = 2
#   Prefix for weekly backup folder
FULL_BACKUP_PREFIX = "backup_"
#   Name of sub folder for full backup
FULL_BACKUP_FOLDER_NAME = "full"
#   Prefix for sub folder with incremental backup
INCREMENTAL_FOLDER_NAME_PREFIX = "inc"
#   Number of threads for backup
PARALLEL_THREAD_NUM = 4
#   Enable SELinux (Set 0 to disable)
ENABLE_SELINUX = False
#   Folder with mysql bin log files
MYSQL_BIN_LOG_PATH = "/mnt/blockstorage/mysql-bin-log"
#   MySQL database folder
MYSQL_DB_PATH = "/var/lib/mysql"
MYSQL_HOST = "127.0.0.1"
MYSQL_PORT = "3306"
MYSQL_USER = "root"


### Configuration of backup script end


def read_args():
    parser = argparse.ArgumentParser(description="Tool to create MySQL backup and restore it.")
    parser.add_argument("-a", "--action", type=str, help="Script action backup or restore", required=True)
    parser.add_argument("-l", "--log_level", type=str, help="Set log level (INFO, DEBUG, WARNING, ERROR)",
                        required=False, default="INFO")
    return parser.parse_args()


def configure_logger(arguments):
    arguments.log_level = str(arguments.log_level).upper()
    if arguments.log_level in logging._nameToLevel:
        level = logging._nameToLevel.get(arguments.log_level)
        logger = logging.getLogger()
        logger.setLevel(level)
        fh = logging.FileHandler('/var/log/backup_mysql.log')
        fh.setLevel(level)
        ch = logging.StreamHandler()
        ch.setLevel(level)
        formatter = logging.Formatter(
            '%(asctime)s [%(filename)s.%(lineno)d] %(processName)s %(levelname)-1s %(name)s - %(message)s')
        ch.setFormatter(formatter)
        fh.setFormatter(formatter)
        logger.addHandler(ch)
        logger.addHandler(fh)
    else:
        raise Exception(f"Can't recognize log level: {arguments.log_level}")


def get_day_of_week():
    today = get_today()
    today_id = today.isoweekday()
    day_of_week = today.strftime("%A").lower()
    logging.debug("Current day of week - %s (%s)", today_id, day_of_week)
    return today_id


def get_today():
    return datetime.now()


def get_first_day_of_week():
    get_today()


def read_backup_info():
    info = f"{FULL_BACKUP_PATH}/xtrabackup_checkpoints"
    with open(info) as f:
        raw_lines = f.readlines()
    lines = []
    for x in raw_lines:
        if x[len(x) - 1] == "\n":
            lines.append(x[:-1])
        else:
            lines.append(x)
    return lines


def is_backup_done(full: bool):
    if full is True:
        t = "backup_type = full-backuped"
    else:
        t = "fg"
    logging.debug("Сhecking for a backup state")
    res = read_backup_info()
    for x in res:
        if x == t:
            return True
        else:
            return False


def do_backup():
    if TODAY_DAY_OF_WEEK == FULL_BACKUP_DAY:
        logging.info("Today is day of full backup. Do full backup first.")
        do_full_backup()
        do_incremental_backup()
    else:
        logging.info("Today is not day of full backup. Do incremental backup only.")
        do_incremental_backup()


def get_full_backup_date():
    return str(get_today().date() - timedelta(days=(TODAY_DAY_OF_WEEK - 1)))


TOOL = "/usr/bin/xtrabackup"


def read_password():
    with open(BACKUP_PASSWORD_FILE) as f:
        a = str(f.readline())
        if a[len(a) - 1] == "\n":
            return a[:-1]
        else:
            return a


def make_backup_command(target_dir, from_dir = ""):
    password = read_password()
    if len(from_dir) == 0:
        res = f"{TOOL} --host={MYSQL_HOST} --port={MYSQL_PORT} --backup --no-lock --parallel={PARALLEL_THREAD_NUM} " \
                 f"--target-dir={target_dir} --user={BACKUP_USER} --password={password}"
        res = res.split(" ")
        logging.debug("Backup command - %s", res)
        return res
    else:
        res = f"{TOOL} --host={MYSQL_HOST} --port={MYSQL_PORT} --backup --no-lock --parallel={PARALLEL_THREAD_NUM} " \
              f"--target-dir={target_dir} --user={BACKUP_USER} --password={password}  --incremental-basedir={from_dir}"
        res = res.split(" ")
        logging.debug("Backup command - %s", res)
        return res


def execute_command(command: List):
    return subprocess.Popen(command, stdout=subprocess.PIPE)


def do_full_backup():
    logging.info("Do full backup")
    execute_command(["mkdir", "-p", FULL_BACKUP_PATH])
    command = make_backup_command(target_dir=FULL_BACKUP_PATH)
    proc = execute_command(command)
    for x in proc.stdout:
        logging.debug(x)


def get_full_backup_path():
    a = f"{WEEKLY_BACKUP_PATH}/{FULL_BACKUP_FOLDER_NAME}"
    logging.debug("Full backup folder - %s", a)
    return a


def is_incremental_backup_done():
    return False


def do_inc_backup_from_backup(previous_backup: str, current_backup: str):
    pass


def do_incremental_backup():
    logging.info("Do incremental backup")
    full_backup_done = is_backup_done(full=True)
    inc_backup_done = is_backup_done(full=False)

    if full_backup_done is True and inc_backup_done is False:
        logging.debug("Full backup exists, incremental backup is not exists. Do incremental backup from full")
        do_inc_backup_from_backup(previous_backup=FULL_BACKUP_PATH, current_backup=INC_BACKUP_PATH_CURRENT)
    elif full_backup_done is True and inc_backup_done is True:
        logging.debug("Full backup exists, incremental backup is exists. Do incremental backup from incremental")
        do_inc_backup_from_backup(previous_backup=INC_BACKUP_PATH_PREVIOUS, current_backup=INC_BACKUP_PATH_CURRENT)
    elif full_backup_done is False:
        logging.debug("Full backup not exists. Do incremental backup from incremental")
        do_full_backup()
    else:
        logging.error("Something new...")


def get_incremental_backup_path():
    a = f"{WEEKLY_BACKUP_PATH}/{INCREMENTAL_FOLDER_NAME_PREFIX}_{str(get_today().date())}"
    logging.debug("Incremental backup folder - %s", a)
    return a


def get_previous_incremental_backup_path():
    logging.debug("Today day - %s, Full backup - %s", TODAY_DAY_OF_WEEK, FULL_BACKUP_DAY)
    for x in range(TODAY_DAY_OF_WEEK, FULL_BACKUP_DAY, -1):
        logging.debug("get_previous_incremental_backup_path - %s", x)
    return ""


if __name__ == '__main__':
    args = read_args()
    configure_logger(arguments=args)

    TODAY_DAY_OF_WEEK = get_day_of_week()
    WEEKLY_BACKUP_PATH = f"{BACKUP_BASE_DIR}/{get_full_backup_date()}"
    FULL_BACKUP_PATH = get_full_backup_path()
    INC_BACKUP_PATH_CURRENT = get_incremental_backup_path()
    INC_BACKUP_PATH_PREVIOUS = get_previous_incremental_backup_path()

    if args.action == "backup":
        logging.info("We are going to do database backup")
        do_backup()
    elif args.action == "restore":
        logging.info("We are going to do database restore")
    else:
        logging.error("Action \"%s\" does not support", args.action)
