#!/usr/bin/env python3.6
import argparse
import logging
import os
from os import listdir
import random
import string
import subprocess
import sys
from datetime import datetime, timedelta
from typing import List

# Configuration of backup script start
#   Name of backup user
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
PARALLEL_THREAD_NUM = 1
#   Enable SELinux (Set 0 to disable)
ENABLE_SELINUX = False
#   Folder with MySQL bin log files
MYSQL_BIN_LOG_PATH = "/mnt/blockstorage/mysql-bin-log"
#   MySQL database folder
MYSQL_DB_PATH = "/var/lib/mysql"
MYSQL_HOST = "127.0.0.1"
MYSQL_PORT = "3306"
MYSQL_USER = "root"

# Configuration of backup script end


BACKUP_TOOL = "/usr/bin/xtrabackup"


def datetime_in_custom_format():
    return get_today().strftime("%Y-%m-%d_%H-%M-%S")


def read_args():
    parser = argparse.ArgumentParser(description="Tool to create MySQL backup and restore it. "
                                                 "Supported actions - backup, restore, copy, export "
                                                 "and import databases.")
    parser.add_argument("-a", "--action", type=str, help="Script action. Supported next operations: "
                                                         "backup, restore, copy, export and import.", required=True)
    parser.add_argument("-l", "--log_level", type=str, help="Set log level (INFO, DEBUG, WARNING, ERROR).",
                        required=False, default="INFO")
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)
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


def get_today() -> datetime:
    return datetime.now()


def read_backup_info(info) -> List:
    with open(info) as f:
        raw_lines = f.readlines()
    logging.debug("read_backup_info - \n%s\n", raw_lines)
    lines = []
    for x in raw_lines:
        if x[len(x) - 1] == "\n":
            lines.append(x[:-1])
        else:
            lines.append(x)
    return lines


def is_backup_done(full: bool, path):
    logging.debug("Looking for backup in %s", path)
    if os.path.exists(path) is False:
        logging.debug("Path %s not found", path)
        return False
    if full is True:
        t = "backup_type = full-backuped"
    else:
        t = "backup_type = incremental"
    logging.debug("Сheck for a backup state")
    info = f"{path}/xtrabackup_checkpoints"
    if os.path.exists(info) is False:
        logging.debug("File %s not found")
        return False
    res = read_backup_info(info)
    for x in res:
        logging.debug("is_backup_done - %s", x)
        if x == t:
            return True
        else:
            return False


def remove_old_backup():
    logging.debug("Remove extra backups, older %s weeks", FULL_BACKUP_COPY_NUM)
    existed = get_exists_backups()
    logging.debug("remove_old_backup.existed - %s", existed)
    for_del_raw = existed[: -1 * FULL_BACKUP_COPY_NUM]
    for x in for_del_raw:
        cmd = f"rm -rf {BACKUP_BASE_DIR}/{x}"
        logging.debug("remove_old_backup.cmd - %s", cmd)
        execute_command(cmd.split(" "))


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


def read_password_from_file():
    with open(BACKUP_PASSWORD_FILE) as f:
        a = str(f.readline())
        if a[len(a) - 1] == "\n":
            return a[:-1]
        else:
            return a


def make_backup_command(target_dir, from_dir=""):
    password = read_password_from_file()

    def __make_command():
        return f"{BACKUP_TOOL} --backup --no-lock --parallel={PARALLEL_THREAD_NUM} --target-dir={target_dir} " \
               f"--user={BACKUP_USER} --password={password}"

    if len(from_dir) == 0:
        res = __make_command()
        res = res.split(" ")
        logging.debug("Backup command (list) - %s", res)
        return res
    else:
        res = f"{__make_command()} --incremental-basedir={from_dir}"
        res = res.split(" ")
        logging.debug("Backup command (list) - %s", res)
        return res


def execute_command(command: List):
    return subprocess.Popen(command, stdout=subprocess.PIPE).wait()


def make_backup(target_backup, source_backup=""):
    execute_command(["mkdir", "-p", target_backup])
    command = make_backup_command(target_dir=target_backup, from_dir=source_backup)
    execute_command(command)


def do_full_backup():
    logging.info("Do full backup")
    make_backup(target_backup=FULL_BACKUP_PATH)
    do_incremental_backup()


def get_full_backup_path():
    a = f"{WEEKLY_BACKUP_PATH}/{FULL_BACKUP_FOLDER_NAME}"
    logging.debug("Full backup folder - %s", a)
    return a


def do_inc_backup_from_backup(previous_backup: str, current_backup: str):
    logging.info("Starting incremental backup from %s to %s", previous_backup, current_backup)
    make_backup(target_backup=current_backup, source_backup=previous_backup)


def do_incremental_backup():
    logging.info("Do incremental backup")
    full_backup_done = is_backup_done(full=True, path=FULL_BACKUP_PATH)
    prev_inc_backup_done = is_backup_done(full=False, path=INC_BACKUP_PATH_PREVIOUS)
    cur_inc_backup_done = is_backup_done(full=False, path=INC_BACKUP_PATH_CURRENT)

    logging.debug("full_backup_done - %s", full_backup_done)
    logging.debug("prev_inc_backup_done - %s", prev_inc_backup_done)
    logging.debug("cur_inc_backup_done - %s", cur_inc_backup_done)

    if full_backup_done is True and prev_inc_backup_done is True and cur_inc_backup_done is False:
        logging.debug("Full backup exists, previous incremental backup is exists. "
                      "Do incremental backup from incremental")
        do_inc_backup_from_backup(previous_backup=INC_BACKUP_PATH_PREVIOUS, current_backup=INC_BACKUP_PATH_CURRENT)
    elif full_backup_done is True and prev_inc_backup_done is False and cur_inc_backup_done is False:
        logging.debug("Full backup exists, incremental backup is not exists. Do incremental backup from full")
        do_inc_backup_from_backup(previous_backup=FULL_BACKUP_PATH, current_backup=INC_BACKUP_PATH_CURRENT)
    elif full_backup_done is True and prev_inc_backup_done is True and cur_inc_backup_done is True:
        logging.error("Incremental backup for today already exists. ")
    elif full_backup_done is True and prev_inc_backup_done is False and cur_inc_backup_done is True:
        logging.error("Incremental backup for today already exists. There are not any previous incremental backup")
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
    logging.debug("Try to find previous incremental backup")
    for x in range(FULL_BACKUP_DAY, TODAY_DAY_OF_WEEK):
        prev_inc = get_today().date() - timedelta(days=int(x))
        path = f"{WEEKLY_BACKUP_PATH}/inc_{prev_inc}"
        logging.debug("get_previous_incremental_backup_path - %s", path)
        if is_backup_done(full=False, path=path) is True:
            return path
    return ""


def list_in_dir(search_path):
    return [dI for dI in os.listdir(search_path) if os.path.isdir(os.path.join(search_path, dI))]


def files_in_dir(search_path):
    return [f for f in listdir(MYSQL_BIN_LOG_PATH) if os.path.isfile(os.path.join(search_path, f))]


def get_exists_backups():
    logging.debug("Get existed backups")
    output = list_in_dir(search_path=BACKUP_BASE_DIR)
    logging.debug("Backup dirs found - %s", output)
    return sorted(output)


def print_exists_backups(backups):
    logging.debug("Print existed backup")
    a = "\n".join(x for x in backups)
    logging.info("Existed backups:\n\n%s\n", a)


def __read_stdin():
    _stdin: str = sys.stdin.readline()
    if _stdin[len(_stdin) - 1] == "\n":
        return _stdin[:-1]
    else:
        return _stdin


def select_exists_backups(existed):
    logging.debug("Select existed backups:")

    a = __read_stdin()
    while a not in existed:
        logging.error("Backup \"%s\" not found in list", a)
        print_exists_backups(existed)
        a = __read_stdin()
    return a


def make_prepare_command(full_backup, apply_log_only, inc_backup=""):
    a = f"{BACKUP_TOOL} --prepare --target-dir={full_backup} "
    if len(inc_backup) > 0:
        a += f"--incremental-dir={inc_backup} "
    if apply_log_only is True:
        a += "--apply-log-only "
    logging.debug("make_prepare_command.a - %s", a)
    t = str(a).split(" ")
    tt = []
    for x in t:
        if len(x) > 0:
            tt.append(x)
    return tt


def prepare_full_backup(backup_path):
    logging.debug("Prepare full backup, %s", backup_path)
    full_backup = f"{backup_path}/{FULL_BACKUP_FOLDER_NAME}"
    a: str = make_prepare_command(full_backup=full_backup, apply_log_only=True)
    logging.debug("Command to prepare backup - %s", a)
    execute_command(make_prepare_command(full_backup=full_backup, apply_log_only=True))
    return full_backup


def get_inc_backup(backup_path):
    r = list_in_dir(backup_path)
    incs = []
    logging.debug("get_inc_backup.r - %s", r)
    for x in r:
        logging.debug("get_inc_backup.x - %s", x)
        if INCREMENTAL_FOLDER_NAME_PREFIX in x:
            incs.append(x)
    return sorted(incs)


def prepare_commands_for_incremental_backups(full_backup, backup_path):
    logging.debug("Prepare incremental backups")
    inc_backups = get_inc_backup(backup_path)
    if len(inc_backups) > 0:
        logging.debug("inc_backups - %s", inc_backups)
        commands = []
        inc_backups_first = inc_backups[:-1]
        logging.debug("inc_backups_first - %s", inc_backups_first)
        for inc in inc_backups_first:
            inc_backup = f"{backup_path}/{inc}"
            logging.debug("inc_backup - %s", inc_backup)
            commands.append(make_prepare_command(full_backup=full_backup, inc_backup=inc_backup, apply_log_only=True))

        inc_backup_last = inc_backups[-1]
        inc_backup = f"{backup_path}/{inc_backup_last}"
        logging.debug("inc_backup_last - %s\ninc_backup - %s", inc_backup_last, inc_backup)
        commands.append(make_prepare_command(full_backup=full_backup, inc_backup=inc_backup, apply_log_only=False))
        logging.debug("List of commands - %s", commands)
        return commands, inc_backup
    else:
        logging.error("There are not found incremental backups in folder %s", backup_path)
        return []


def make_backup_path(backup_dir):
    return f"{BACKUP_BASE_DIR}/{backup_dir}"


def execute_prepare_commands(cmds):
    if len(cmds) > 0:
        for x in cmds:
            logging.debug("Execute command - %s", x)
            execute_command(x)


def prepare_backup(prev_step: bool):
    if prev_step is False:
        return False, ""
    if os.path.exists(MYSQL_DB_PATH) is False:
        backup_list = get_exists_backups()
        print_exists_backups(backup_list)
        backup_dir = select_exists_backups(backup_list)
        logging.info("Are you sure you want to restore this backup? [Y(yes) or N(no)]: ")

        if __read_stdin().lower() in ("y", "yes"):
            backup_path = make_backup_path(backup_dir)
            full_backup = prepare_full_backup(backup_path)
            prepare_cmds, last_inc_backup = prepare_commands_for_incremental_backups(full_backup=full_backup,
                                                                                     backup_path=backup_path)
            execute_prepare_commands(cmds=prepare_cmds)
            return True, full_backup, last_inc_backup, backup_path
        else:
            return False, "", "", ""
    else:
        logging.error("Previous instance is exists, remove it before prepare restoration")
        return False, "", "", ""


def mysql_stop():
    cmd = "systemctl stop mysql"
    logging.debug("Stopping MySQL - %s", cmd)
    execute_command(cmd.split(" "))


def mysql_start(prev_step):
    if prev_step is False:
        return False
    cmd = "systemctl start mysql"
    logging.debug("Starting MySQL - %s", cmd)
    execute_command(cmd.split(" "))
    return True


def generate_random_string(size=15, chars=string.ascii_letters + string.ascii_uppercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))


def rename_exist_instance():
    logging.debug("Try to rename exists instance to new name")
    global MYSQL_DB_PATH_NEW
    MYSQL_DB_PATH_NEW = f"{MYSQL_DB_PATH}_{generate_random_string()}"
    logging.debug("New name for exists instance - %s", MYSQL_DB_PATH_NEW)
    if os.path.exists(MYSQL_DB_PATH):
        execute_command(["mv", MYSQL_DB_PATH, MYSQL_DB_PATH_NEW])
    else:
        logging.warning("Path %s not found", MYSQL_DB_PATH)


def remove_exists_instance():
    mysql_stop()
    rename_exist_instance()


def restore_db(prev_step, full_backup):
    if prev_step is False:
        return False
    if os.path.exists(full_backup):
        cmd = f"{BACKUP_TOOL} --copy-back --target-dir={full_backup} --datadir={MYSQL_DB_PATH}"
        logging.debug("Execute command - %s", cmd)
        execute_command(cmd.split(" "))
        return True


def restore_folder_permissions(prev_step):
    if prev_step is False:
        return False
    cmd = f"chown mysql:mysql {MYSQL_DB_PATH} -R"
    logging.debug("restore_folder_permissions: chown - %s", cmd)
    execute_command(cmd.split(" "))

    cmd = f"chmod 775 {MYSQL_DB_PATH} -R"
    logging.debug("restore_folder_permissions: chmod - %s", cmd)
    execute_command(cmd.split(" "))

    if ENABLE_SELINUX is True:
        a = str(f"semanage fcontext -a -t mysqld_db_t \"{MYSQL_DB_PATH}(/.*)?\"")
        logging.debug("restore_folder_permissions: semanage - %s", a)
        execute_command(a.split(" "))
        a = str(f"restorecon -vrF {MYSQL_DB_PATH}")
        logging.debug("restore_folder_permissions: restorecon - %s", a)
        execute_command(a.split(" "))
    return True


def execute_command_in_bash(command):
    f_name = __make_temp_bash()
    save_to_file(file_path=f_name, text=command)
    execute_command(f"/usr/bin/bash {f_name}".split(" "))
    return f_name


def apply_bin_log(password):
    cmd = f"/usr/bin/mysql --user={MYSQL_USER} --host={MYSQL_HOST} --port={MYSQL_PORT} --password={password} " \
          f"< {BIN_LOG_IN_SQL}"
    logging.debug("apply_bin_log - %s", cmd)
    global APPLY_BIN_LOG_FILE
    APPLY_BIN_LOG_FILE = execute_command_in_bash(command=cmd)


def rename_restored_backup(backup_dir):
    global RENAME_RESTORED_BACKUP_NEW
    RENAME_RESTORED_BACKUP_NEW = f"{backup_dir}_{generate_random_string()}"
    cmd = f"mv {backup_dir} {RENAME_RESTORED_BACKUP_NEW}"
    logging.debug("rename_restored_backup - %s", cmd)
    execute_command(cmd.split(" "))


def purge_binary_logs(password):
    cmd = f"/usr/bin/mysql --user={MYSQL_USER} --host={MYSQL_HOST} --port={MYSQL_PORT} --password={password} " \
          f"--execute='PURGE BINARY LOGS BEFORE NOW();'"
    global PURGE_BINARY_LOGS_FILE
    PURGE_BINARY_LOGS_FILE = execute_command_in_bash(command=cmd)


def make_binlog_info_file_path(path):
    return f"{path}/xtrabackup_binlog_info"


def get_binlog_info_file(last_inc_backup, full_backup):
    logging.debug("get_binlog_info_file.last_inc_backup - %s", last_inc_backup)
    logging.debug("get_binlog_info_file.full_backup - %s", full_backup)
    if os.path.exists(last_inc_backup):
        return make_binlog_info_file_path(path=last_inc_backup)
    else:
        return make_binlog_info_file_path(path=full_backup)


def __read_file(binlog_info):
    def __list_to_tuple(b):
        return tuple(str(b).split("\t"))

    with open(binlog_info) as f:
        a = str(f.readline())
        logging.debug("__read_file.a - %s", a)
        if a[len(a) - 1] == "\n":
            return __list_to_tuple(a[:-1])
        else:
            return __list_to_tuple(a)


def get_bin_files(mysqlbin_file):
    res_raw = sorted(files_in_dir(MYSQL_BIN_LOG_PATH))[:-1]
    logging.debug(res_raw)
    mysql_bin_id = res_raw.index(mysqlbin_file)
    res = res_raw[mysql_bin_id:len(res_raw)]
    logging.debug(res)
    path_bin_files = []
    for x in res:
        path_bin_files.append(f"{MYSQL_BIN_LOG_PATH}/{x}")
    logging.debug(path_bin_files)
    return path_bin_files


def convert_bin_files_to_sql(bin_files, lsn, damage_time):
    def __bin_file_to_line():
        return " ".join(x for x in bin_files)

    if len(damage_time) == 0:
        cmd = f"mysqlbinlog --start-position={lsn} {__bin_file_to_line()}"
    else:
        cmd = f"mysqlbinlog --start-position={lsn}  --stop-datetime={damage_time} {__bin_file_to_line()}"
    cmd += f" > {BIN_LOG_IN_SQL}"

    logging.debug("convert_bin_files_to_sql - %s", cmd)
    global CONVERTED_BINFILES_SQL
    CONVERTED_BINFILES_SQL = execute_command_in_bash(command=cmd)


def save_to_file(file_path, text):
    with open(file_path, "w") as f:
        f.write(f"{text}\n")


def __make_temp_bash():
    return f"/tmp/{generate_random_string()}.sh"


def restore_databases():
    remove_exists_instance()
    prev_step, full_backup, last_inc_backup, backup_dir = prepare_backup(True)
    prev_step = restore_db(prev_step, full_backup)
    prev_step = restore_folder_permissions(prev_step)
    prev_step = mysql_start(prev_step)

    password = ""
    if prev_step is True:
        logging.info("Do you want apply MySQL binary logs? [Y(yes) or N(no)]: ")

        if __read_stdin().lower() in ("y", "yes"):
            password = read_password_from_stdin()
            logging.info("Enter time when you database was damaged (in format like 2018-07-15T19:27:00)")
            damage_time = __read_stdin()
            binlog_info = get_binlog_info_file(last_inc_backup=last_inc_backup, full_backup=full_backup)
            logging.debug("binlog_info - %s", binlog_info)
            mysqlbin_file, lsn, _ = __read_file(binlog_info)
            logging.debug("mysqlbin_file - %s, lsn - %s", mysqlbin_file, lsn)
            bin_files = get_bin_files(mysqlbin_file)
            convert_bin_files_to_sql(bin_files=bin_files, lsn=lsn, damage_time=damage_time)
            apply_bin_log(password=password)
    rename_restored_backup(backup_dir)
    do_full_backup()
    purge_binary_logs(password=password)


def read_password_from_stdin():
    logging.info("Enter password for user %s@%s:%s", MYSQL_USER, MYSQL_HOST, MYSQL_PORT)
    return __read_stdin()


def get_source_db_name():
    logging.info("Enter name of source DB:")
    name = __read_stdin()
    if len(name) != 0:
        return name
    else:
        logging.error("Database name can not be empty. Please, try again!")
        get_source_db_name()


def get_target_db_host():
    logging.info("Enter database host to import dump to database (if empty will use host \"127.0.0.1\", "
                 "ie \"localhost\"):")
    val = __read_stdin()
    if len(val) == 0:
        return "127.0.0.1"
    else:
        return val


def get_target_db_port():
    logging.info("Enter database port to import dump to database (if empty will use port \"3306\"):")
    val = __read_stdin()
    if len(val) == 0:
        return "3306"
    else:
        return val


def get_target_db_user():
    logging.info("Enter database user to import dump to database (if empty will use user \"root\"):")
    val = __read_stdin()
    if len(val) == 0:
        return "root"
    else:
        return val


def get_target_db_pass():
    logging.info("Enter user's password to import dump to database:")
    val = __read_stdin()
    if len(val) != 0:
        return val
    else:
        logging.error("Database name can not be empty. Please, try again!")
        get_target_db_pass()


def get_target_db_name():
    logging.info("Enter name of target DB:")
    val = __read_stdin()
    if len(val) != 0:
        return val
    else:
        logging.error("Database name can not be empty. Please, try again!")
        get_target_db_name()


def get_export_folder():
    logging.info("Enter dump folder name:")
    destination_folder = __read_stdin()
    logging.debug("destination folder - %s", destination_folder)
    if os.path.isdir(destination_folder) and os.path.exists(destination_folder):
        if destination_folder is not None:
            return destination_folder
    else:
        logging.error("Folder name is empty or folder does not exists!")
        get_export_folder()


def export_db(db_name, db_pass, destination_folder=""):
    if len(destination_folder) == 0:
        destination_folder = "/tmp"

    dump_file = f"{destination_folder}/{db_name}_{datetime_in_custom_format()}.sql.gz"
    cmd = f"/usr/bin/mysqldump --user={MYSQL_USER} --host={MYSQL_HOST} --port={MYSQL_PORT} " \
          f"--password={db_pass} --lock-tables=false " \
          f"--events --routines --triggers {db_name} | gzip > {dump_file}"
    logging.debug("export_db.cmd - %s", cmd)
    return dump_file, execute_command_in_bash(command=cmd)


def import_db(db_name, db_pass, dump_file, db_host="", db_port="", db_user=""):
    if len(db_host) == 0 and len(db_port) == 0 and len(db_user) <= 0:
        db_host = MYSQL_HOST
        db_port = MYSQL_PORT
        db_user = MYSQL_USER

    cmd = f"zcat {dump_file} | " \
          f"/usr/bin/mysql --user={db_user} --host={db_host} --port={db_port} --password={db_pass} {db_name}"
    logging.debug("import_db.cmd - %s", cmd)
    return execute_command_in_bash(command=cmd)


def copy_db():
    password = read_password_from_stdin()
    source_db = get_source_db_name()
    target_db = get_target_db_name()
    print(f"Database \"{source_db}\" will copy to \"{target_db}\"\n"
          f"Verify that database \"{target_db}\" exists on server!")
    print(f"Are you ready to continue? Y(yes) or N(no)")
    answer = __read_stdin().lower()
    if answer in ("y", "yes"):
        dump_file, export_db_sh = export_db_to_file(db_name=source_db, db_pass=password)
        import_db_sh = import_db(db_name=target_db, db_pass=password, dump_file=dump_file)
        logging.warning("\n"
                        "Source database - \"%s\"; \nTarget database - \"%s\"\n"
                        "Verify that new copy is work properly!\n"
                        "Remove next file:\n"
                        "\tExport source DB script - %s\n"
                        "\tImport source DB script - %s\n"
                        "\tDump file - %s", source_db, target_db, export_db_sh, import_db_sh,
                        dump_file)
    else:
        logging.info("Bye!")


def get_dump_file():
    logging.info("Enter full path to dump file")
    dump_file = __read_stdin()
    if os.path.exists(dump_file):
        return dump_file
    else:
        logging.error("Can not find dump file, please try again!")
        get_dump_file()


def import_db_from_file():
    dump_file = get_dump_file()
    db_host = get_target_db_host()
    db_port = get_target_db_port()
    db_name = get_target_db_name()
    db_user = get_target_db_user()
    db_pass = get_target_db_pass()
    print(f"To import database from file \"{dump_file}\" with next credentials:\n"
          f"\tDB Host: {db_host}\n"
          f"\tDB Port: {db_port}\n"
          f"\tDB Name: {db_name}\n"
          f"\tDB User: {db_user}\n"
          f"\tDB Password: {db_pass}")
    print(f"Verify that database \"{db_name}\" exists on server!")
    print(f"Verify that user \"{db_user}\" can create tables in database \"{db_name}\"!")
    print(f"Are you ready to import? Y(yes) or N(no)")
    answer = __read_stdin().lower()
    if answer in ("y", "yes"):
        logging.info("Start import file %s to database %s", dump_file, db_name)
        import_sh = import_db(db_host=db_host,
                              db_port=db_port,
                              db_name=db_name,
                              db_user=db_user,
                              db_pass=db_pass,
                              dump_file=dump_file)
        logging.warning(f"\n\nVerify that database imported successful and remove next files:\n"
                        f"\tImport shell script - {import_sh}\n"
                        f"\tDump file - {dump_file}")
    else:
        logging.info("Bye!")


def export_db_to_file(db_name="", db_pass=""):
    if len(db_name) == 0 and len(db_pass) == 0:
        db_pass = read_password_from_stdin()
        db_name = get_source_db_name()
        export_dir = get_export_folder()
        dump_file, sh = export_db(db_name=db_name, db_pass=db_pass, destination_folder=export_dir)
        logging.warning(f"\n"
                        f"\tDump file saved - {dump_file}\n"
                        f"\tShell script to make dump - {sh}")
        return dump_file, sh
    return export_db(db_name=db_name, db_pass=db_pass)


if __name__ == '__main__':
    args = read_args()
    configure_logger(arguments=args)
    BIN_LOG_IN_SQL = f"/tmp/converted_mysql_bin_logs_{datetime_in_custom_format()}.sql"

    TODAY_DAY_OF_WEEK = get_day_of_week()
    WEEKLY_BACKUP_PATH = f"{BACKUP_BASE_DIR}/{FULL_BACKUP_PREFIX}{get_full_backup_date()}"
    FULL_BACKUP_PATH = get_full_backup_path()
    INC_BACKUP_PATH_CURRENT = get_incremental_backup_path()
    INC_BACKUP_PATH_PREVIOUS = get_previous_incremental_backup_path()
    APPLY_BIN_LOG_FILE = None
    PURGE_BINARY_LOGS_FILE = None
    CONVERTED_BINFILES_SQL = None
    MYSQL_DB_PATH_NEW = None
    RENAME_RESTORED_BACKUP_NEW = None

    if args.action.lower() == "backup":
        logging.info("We are going to do database backup")
        do_backup()
        remove_old_backup()
    elif args.action.lower() == "restore":
        logging.info("We are going to do database restore")
        restore_databases()
        logging.warning(f"\n"
                        "Next steps:\n"
                        "Verify that your MySQL instance is work properly;\n"
                        "If your MySQL instance is work properly remove next files and folders:\n"
                        "Bash script that apply converted mysqlbinlog files to DB - %s\n"
                        "Bash script to purge MySQL Binlog files - %s\n"
                        "Converted to SQL MySQL binary logs - %s\n"
                        "Old MySQL instance - %s\n"
                        "Folder with previous full backup (before restoration) - %s",
                        APPLY_BIN_LOG_FILE, PURGE_BINARY_LOGS_FILE, CONVERTED_BINFILES_SQL, MYSQL_DB_PATH_NEW,
                        RENAME_RESTORED_BACKUP_NEW)
    elif args.action.lower() == "copy":
        logging.info("Start COPY one database to another one")
        copy_db()
    elif args.action.lower() == "export":
        logging.info("Start export database to file")
        export_db_to_file()
    elif args.action.lower() == "import":
        logging.info("Start import database from file")
        import_db_from_file()
    else:
        logging.error("Action \"%s\" does not support", args.action)
