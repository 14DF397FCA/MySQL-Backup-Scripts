**Script backup.py is work only Python3.6!**

You can find Instruction about installation Python3.6 on CentOS 7 on link below:
https://www.digitalocean.com/community/tutorials/how-to-install-python-3-and-set-up-a-local-programming-environment-on-centos-7

# Usage

```
usage: backup.py [-h] -a ACTION [-l LOG_LEVEL]

Tool to create MySQL backup and restore it. Supported actions - backup,
restore, copy, export and import databases.

optional arguments:
  -h, --help            show this help message and exit
  -a ACTION, --action ACTION
                        Script action. Supported next operations: backup,
                        restore, copy, export and import.
  -l LOG_LEVEL, --log_level LOG_LEVEL
                        Set log level (INFO, DEBUG, WARNING, ERROR).
```

# Examples
## Make database backup
```
python3.6 ./backup.py -a backup
```
or
```
./backup.py -a backup
```
## Restore from database backup
```
python3.6 ./backup.py -a restore
```
or
```
./backup.py -a restore
```
## Copy one database to another one on same server
```
python3.6 ./backup.py -a copy
```
or
```
./backup.py -a copy
```
## Export database to file
```
python3.6 ./backup.py -a export
```
or
```
./backup.py -a export
```
## Import database from file
```
python3.6 ./backup.py -a import
```
or
```
./backup.py -a import
```