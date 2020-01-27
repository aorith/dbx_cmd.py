# dbx_cmd.py
Upload encrypted backups to Dropbox

# Info
I made this script because I store all my files across devices using [Syncthing](https://syncthing.net/) and wanted a Cloud backup too without exposing all my personal data, at least until AES256 is broken =)

# Installation

Currently it's only working on Linux (I have it scheduled in the crontab of my SBC - Odroid HC1).
You'll need the following python packages:

`pip install dropbox --user`

Open dbx_cmd.py and edit the following variables if needed:
```python
SYMMETRIC_ENCRYPTION = False
TMP_PATH = os.path.join('/tmp')
SECRETS_CFG = os.path.join(os.environ['HOME'], 'secret/dbx_cmd.cfg')
```
* SYMMETRIC_ENCRYPTION --> If set to True it will use symmetric encryption [Symmetric-key algorithm](https://en.wikipedia.org/wiki/Symmetric-key_algorithm). Files will be encrypted using the password defined in the .cfg file.
On the other hand, if set to False it will use asymmetric encryption [Public-key cryptography](https://en.wikipedia.org/wiki/Public-key_cryptography) and files will be encrypted using the recipient defined in USERID at the .cfg file.

* TMP_PATH --> Temporal path to compress and encrypt files before uploading to Dropbox.

* SECRETS_CFG --> Should point to a valid .cfg file using below syntax:

```cfg
[DBX]
TOKEN = <dropbox api token>
USERID = <userid of the recipient if using Asymmetric encryption, for ex: john@maildir.com>
PASSWORD = <password without quotes, only used in Symmetric encryption>
```

# Usage

The idea is to have it scheduled in your crontab to make nightly backups.

## Backup
The script backups entire folders, so imagine you have this folder on your server /media/data/Photos with all your personal photos.

Run:

```sh
/usr/bin/python3 /path/to/dbx_cmd.py backup -l /media/data/Photos -r /BACKUPS/Photos -m 5
```

To upload an encrypted copy of the folder Photos to your Dropbox account at /Backup/Photos/YYYYMMDDHHMMSS-md5sum.tar.xz.gpg.
The switch `-m` tells the script how many backups of that folder to store, it won't upload it again if it already exists (md5sum to check modifications).

## List
To list remote folders at Dropbox use:

```sh
/usr/bin/python3 /path/to/dbx_cmd.py list -f /Backup/Photos
```

Example output:

```
[2020-01-27 19:00:23,336][INFO] ************ Listing results *************

[2020-01-27 19:00:23,336][INFO] /Backup/Photos/20200127190003-ba5db5b5a12013247d8e4115c0b51c2f.tar.xz.gpg  0.04MB
```

## Download

To download stored files in Dropbox to your current path use:

```sh
/usr/bin/python3 /path/to/dbx_cmd.py download -f /Backup/Photos/20200127190003-ba5db5b5a12013247d8e4115c0b51c2f.tar.xz.gpg
```

# Logs

Logs are stored by default in `$HOME/logs`, one log is created for each unique backup folder. You can easily change the path in the script.

# How does it work

Basically the script does the following in backup mode:
1. Creates a tarfile with all the contents of the local folder.
2. Checks tarfile md5sum, gets a list of current backups in the remote folder and compares them, if md5sum matches it doesn't upload anything and stops here.
3. Compresses the tarfile with lzma.
4. Encrypts the .tar.xz file with gpg.
5. Uploads it to Dropbox.
6. Cleans old backups depending of the `-m` switch, so if you have `-m 5` and this is the 6th backup, it will delete the oldest.

# Warning

If you would like to use this script, I recommend that you make some tests first, backup a random folder and try to download it and decrypt using `gpg -d file.tar.xz.gpg > file.tar.xz` to check that it works correctly, if you are using Symmetric encryption make sure not to lose your password, if you are using Asymmetric encryption don't lose your private key =)
