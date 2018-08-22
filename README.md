**Script backup.py is work only Python3.6!**

You can find Instruction about installation Python3.6 on CentOS 7 on link below:
https://www.digitalocean.com/community/tutorials/how-to-install-python-3-and-set-up-a-local-programming-environment-on-centos-7

# Usage

```
python3.6 ./backup.py -h
usage: backup.py [-h] -a ACTION [-l LOG_LEVEL]

Tool to create MySQL backup and restore it.

optional arguments:
  -h, --help            show this help message and exit
  -a ACTION, --action ACTION
                        Script action backup or restore
  -l LOG_LEVEL, --log_level LOG_LEVEL
                        Set log level (INFO, DEBUG, WARNING, ERROR)
```

# Examples
## Make database backup
```
python3.6 ./backup.py -a backup
```
## Restore from database backup
```
python3.6 ./backup.py -a restore
```