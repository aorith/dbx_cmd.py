Deprecated
==========
Now I'm using this instead: <https://github.com/aorith/st-backup>

# dbx_cmd.py
Upload encrypted backups to Dropbox

## Info
I made this script because I store all my files across devices using [Syncthing](https://syncthing.net/) and wanted a Cloud backup too without exposing all my personal data, at least until AES256 is broken =)

## Installation

Currently it's only working on Linux (I have it scheduled in the crontab of my SBC - Odroid HC1).
You'll need the following python packages:

`pip install dropbox --user`

Open dbx_cmd.py and edit the following variables as needed:
```python
SYMMETRIC_ENCRYPTION = False
TMP_PATH = os.path.join(os.environ['HOME'], 'tmp')
LOGS_PATH = os.path.join(os.environ['HOME'], 'logs')
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
To obtain a Dropbox API key go to [https://www.dropbox.com/developers/apps](https://www.dropbox.com/developers/apps)

## Usage

The idea is to have it scheduled in your crontab to make nightly backups.

### Backup
The script backups entire folders, so imagine you have this folder on your server /media/data/Photos with all your personal photos.

Run:

```sh
/usr/bin/python3 /path/to/dbx_cmd.py backup -l /media/data/Photos -r /BACKUPS/Photos -m 5
```

To upload an encrypted copy of the folder Photos to your Dropbox account at /Backup/Photos/YYYYMMDDHHMMSS-md5sum.tar.xz.gpg.
The switch `-m` tells the script how many backups of that folder to store, it won't upload it again if it already exists (md5sum to check modifications).

### List
To list remote folders at Dropbox use:

```sh
/usr/bin/python3 /path/to/dbx_cmd.py list -f /Backup/Photos
```

Example output:

```
[2020-01-27 19:00:23,336][INFO] ************ Listing results *************

[2020-01-27 19:00:23,336][INFO] /Backup/Photos/20200127190003-ba5db5b5a12013247d8e4115c0b51c2f.tar.xz.gpg  0.04MB
```

### Download

To download stored files in Dropbox to your current path use:

```sh
/usr/bin/python3 /path/to/dbx_cmd.py download -f /Backup/Photos/20200127190003-ba5db5b5a12013247d8e4115c0b51c2f.tar.xz.gpg
```

## Logs

Logs are stored by default in `$HOME/logs`, one log is created for each unique backup folder. You can easily change the default path modifying LOGS_PATH variable.

## How does it work

Basically the script does the following in backup mode:
1. Creates a tarfile with all the contents of the local folder.
2. Checks tarfile md5sum, gets a list of current backups in the remote folder and compares them, if md5sum matches it doesn't upload anything and stops here.
3. Compresses the tarfile with lzma.
4. Encrypts the .tar.xz file with gpg.
5. Uploads it to Dropbox.
6. Cleans old backups depending of the `-m` switch, so if you have `-m 5` and this is the 6th backup, it will delete the oldest.

### Sample backup run log

<pre>
$ /usr/bin/python3 /home/aorith/bin/dbx_cmd.py backup -l /media/datos/Syncthing/SYNC_STUFF -r /ODROID_BACKUPS/SYNC_STUFF -m 12
[2020-02-14 19:58:47,207][INFO] ------------------------------
[2020-02-14 19:58:47,208][INFO] STARTING...
[2020-02-14 19:58:47,208][INFO] ------------------------------
[2020-02-14 19:58:47,208][INFO] ['/home/aorith/bin/dbx_cmd.py', 'backup', '-l', '/media/datos/Syncthing/SYNC_STUFF', '-r', '/ODROID_BACKUPS/SYNC_STUFF', '-m', '12']
[2020-02-14 19:58:47,208][INFO] ------------------------------
[2020-02-14 19:58:47,949][INFO] Starting tarball process...
[2020-02-14 19:58:55,529][INFO] Function create_tar() finished in 7.580 seconds.
[2020-02-14 19:58:55,530][INFO] Calculating md5sum of /home/aorith/tmp/20200214195847.tar.
[2020-02-14 19:58:56,437][INFO] Function md5() finished in 0.907 seconds.
[2020-02-14 19:58:58,663][INFO] Starting to compress /home/aorith/tmp/20200214195847.tar
[2020-02-14 19:59:56,382][INFO] Processing... 64.0/135.5 MB - elapsed 57.58 seconds (1.11 MB/s)
[2020-02-14 20:00:58,222][INFO] Processing... 128.0/135.5 MB - elapsed 119.31 seconds (1.04 MB/s)
[2020-02-14 20:01:04,554][INFO] Processing... 135.5/135.5 MB - elapsed 125.64 seconds (10.11 MB/s)
[2020-02-14 20:01:05,064][INFO] Function compress() finished in 126.402 seconds.
[2020-02-14 20:01:05,065][INFO] Starting to encrypt /home/aorith/tmp/20200214195847.tar.xz
[2020-02-14 20:01:15,793][INFO] Function gpg_encrypt() finished in 10.728 seconds.
[2020-02-14 20:01:15,794][INFO] File /home/aorith/tmp/20200214195847-0513c4231e4947e310e6df17711081c5.tar.xz.gpg not in Dropbox, uploading...
[2020-02-14 20:01:16,364][INFO] Disk space used: 4193.35/6400.00 MBs (66.00%).
[2020-02-14 20:01:16,365][INFO] Uploading /home/aorith/tmp/20200214195847-0513c4231e4947e310e6df17711081c5.tar.xz.gpg
[2020-02-14 20:01:19,370][INFO] Processing... 32.0/104.85 MB - elapsed 3.01 seconds (10.65 MB/s)
[2020-02-14 20:01:21,880][INFO] Processing... 64.0/104.85 MB - elapsed 5.51 seconds (12.75 MB/s)
[2020-02-14 20:01:24,601][INFO] Processing... 96.0/104.85 MB - elapsed 8.24 seconds (11.76 MB/s)
[2020-02-14 20:01:27,184][INFO] Processing... 104.85/104.85 MB - elapsed 10.82 seconds (12.4 MB/s)
[2020-02-14 20:01:27,185][INFO] Function upload_file() finished in 11.391 seconds.
[2020-02-14 20:01:27,186][INFO] File uploaded successfully to /ODROID_BACKUPS/SYNC_STUFF/20200214195847-0513c4231e4947e310e6df17711081c5.tar.xz.gpg
[2020-02-14 20:01:27,186][INFO] Cleaning...
[2020-02-14 20:01:28,138][INFO] Function backup() finished in 160.189 seconds.
[2020-02-14 20:01:28,139][INFO] ------------------------------
[2020-02-14 20:01:28,692][INFO] Disk space used: 4298.20/6400.00 MBs (67.00%).
[2020-02-14 20:01:28,692][INFO] END.
[2020-02-14 20:01:28,693][INFO] ------------------------------
[2020-02-14 20:01:28,698][INFO] Function main() finished in 161.500 seconds.
</pre>

## Warning

If you would like to use this script, I recommend that you make some tests first, backup a random folder and try to download it and decrypt using `gpg -d file.tar.xz.gpg > file.tar.xz` to check that it works correctly, if you are using Symmetric encryption make sure not to lose your password, if you are using Asymmetric encryption don't lose your private key =)
