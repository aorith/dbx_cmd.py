#!/usr/bin/env python3
import os
import sys
import argparse
import configparser
import subprocess
import lzma
import tarfile
from time import time
from datetime import datetime
import logging
import hashlib
from logging.handlers import RotatingFileHandler
import dropbox


# Settings
SYMMETRIC_ENCRYPTION = False
TMP_PATH = os.path.join(os.environ['HOME'], 'tmp')
LOGS_PATH = os.path.join(os.environ['HOME'], 'logs')
SECRETS_CFG = os.path.join(os.environ['HOME'], 'secret/dbx_cmd.cfg')
""" Config file example:
[DBX]
TOKEN = <dropbox api token>
USERID = <userid>  (userid or email of your gpg key)
PASSWORD = <password>  (password if using symmetric encryption)
"""


def timer(function):
    """
    wrapper timer function, use with a decorator --> @timer
    """
    logger = logging.getLogger(__name__)

    def wrapper(*args, **kwargs):
        before = time()
        rv = function(*args, **kwargs)
        elapsed = time() - before
        logger.info('Function %s() finished in %.3f seconds.',
                    function.__name__, elapsed)
        return rv
    return wrapper


@timer
def md5(fname):
    logger = logging.getLogger(__name__)
    fname = os.path.realpath(fname)
    chunk_size = 4 * 1024 * 1024
    hash_md5 = hashlib.md5()
    logger.info("Calculating md5sum of %s.", fname)
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def by_chunk_info(file_size, chunk_size, processed, t0, elapsed):
    logger = logging.getLogger(__name__)
    t1 = time()
    elapsed_now = t1 - t0
    elapsed = elapsed + elapsed_now
    speed = round((chunk_size / elapsed_now) / (1024 * 1024), 2)
    processed = round(processed/(1024 * 1024), 2)
    file_size = round(file_size/(1024 * 1024), 2)
    msg = "Processing... {}/{} MB - elapsed {} seconds ({} MB/s)".format(
        processed,
        file_size,
        round(elapsed, 2),
        speed
    )
    logger.info(msg)
    return elapsed


@timer
def create_tar(fpath, tar_path):
    logger = logging.getLogger(__name__)
    logger.info("Starting tarball process...")
    try:
        with tarfile.open(tar_path, "w") as tar:
            tar.add(fpath, arcname=os.path.basename(fpath))
    except Exception as ex:
        txt = "Failed to tar file.\nException of type {0}. Arguments:\n{1!r}"
        msg = txt.format(type(ex).__name__, ex.args)
        logger.error(msg)
        os.remove(tar_path)
        sys.exit(1)
    return tar.name


@timer
def compress(fname):
    logger = logging.getLogger(__name__)
    logger.info("Starting to compress %s", fname)
    file_size = os.path.getsize(fname)
    elapsed = 0
    try:
        chunk_size = 64 * 1024 * 1024
        fnamexz = fname + '.xz'
        with open(fname, 'rb') as fh:
            with lzma.open(fnamexz, "w") as f:
                while True:
                    t0 = time()
                    chunk = fh.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    elapsed = by_chunk_info(
                        file_size, chunk_size, f.tell(), t0, elapsed)

    except Exception as ex:
        txt = "Failed to compress file.\nException of type {0}. Arguments:\n{1!r}"
        msg = txt.format(type(ex).__name__, ex.args)
        logger.error(msg)
        os.remove(fname)
        sys.exit(1)

    os.remove(fname)
    return fnamexz


@timer
def gpg_encrypt(fname, userid=None, password=None):
    logger = logging.getLogger(__name__)
    logger.info("Starting to encrypt %s", fname)

    if SYMMETRIC_ENCRYPTION:
        cipher_ops = "--s2k-mode 3 --s2k-count 65011712 --s2k-digest-algo SHA512 --s2k-cipher-algo AES256"
        cmd = "gpg {} --passphrase {} --batch --quiet --yes -c {}".format(
            cipher_ops,
            password,
            fname
        )
    else:
        cmd = "gpg -e -u {} -r {} --always-trust --quiet --yes {}".format(
            userid,
            userid,
            fname
        )

    try:
        result = subprocess.check_output(
            cmd, stderr=subprocess.STDOUT, shell=True
        )
    except Exception as ex:
        txt = "Process failed while trying to encrypt: {0}.\nException of type {1}."
        msg = txt.format(fname, type(ex).__name__)
        logger.error(msg)
        os.remove(fname)
        sys.exit(1)
    os.remove(fname)
    return fname + '.gpg'


class Dbx:
    def __init__(self, args, cfg, timeout=2000):
        self.logger = logging.getLogger(__name__)
        self.token = cfg[0]
        self.userid = cfg[1]
        self.password = cfg[2]
        self.dbx = dropbox.Dropbox(self.token, timeout=timeout)
        self.args = args
        self.ext = ".tar.xz.gpg"
        self.remote_folder = ""
        self.local_folder = ""
        self.max_files = 3
        self.to_download = ""
        self.path = ""
        self.mode = args.mode_option

        if self.mode == 'backup':
            self.remote_folder = os.path.normpath(self.args.remote_folder[0])
            if not self.remote_folder.startswith("/"):
                self.remote_folder = os.path.normpath("/" + self.remote_folder)

            self.local_folder = os.path.realpath(args.local_folder[0])
            self.max_files = args.max_files[0]
        elif self.mode == 'download' or self.mode == 'list':
            self.path = os.path.normpath(args.file[0])
            if not self.path.startswith("/"):
                self.path = os.path.normpath("/" + self.path)
            self.to_download = self.path

    def check_space(self, file_size=None):
        """ check space in dropbox, if file_size is not None
        checks if there is enough space to upload it """
        sp = self.dbx.users_get_space_usage()
        used = sp.used
        total = sp.allocation.get_individual().allocated
        perc = round((used * 100) / total, 0)
        self.logger.info("Disk space used: %.2f/%.2f MBs (%.2f%s).",
                         round(used / (1024*1024), 2),
                         round(total / (1024*1024), 2),
                         perc,
                         '%'
                         )
        if file_size is not None:
            if total - used < file_size:
                return False
        return True

    def is_file(self, path):
        """ Checks if path is a folder, file or doesn't exists.
        return 0 --> is a file
        return 1 --> is a folder
        return 2 --< doesn't exist
        """
        try:
            if isinstance(self.dbx.files_get_metadata(path), dropbox.files.FileMetadata):
                return 0
            else:
                return 1
        except:
            return 2

    def remote_list(self, path):
        try:
            ret = self.is_file(path)
            if ret == 0:
                entries = []
                entries.append(self.dbx.files_get_metadata(path))
            elif ret == 1:
                entries = self.dbx.files_list_folder(path).entries
            else:
                raise Exception("Not Found: remote_list({})".format(path))
        except Exception as ex:
            txt = "Exception of type {0}. Arguments:\n{1!r}"
            msg = txt.format(type(ex).__name__, ex.args)
            self.logger.error(msg)
            sys.exit(1)
        return entries

    def file_exists(self, md5_sum, folder):
        ret = self.is_file(folder)
        if ret == 0:
            self.logger.error(
                "Must select a folder to upload backups. \'%s\' is a file.", folder)
        elif ret == 1:

            entries = self.remote_list(folder)
            for entry in entries:
                if entry.name.split("-")[1].split(".")[0] == md5_sum:
                    return True
            return False
        else:
            self.logger.info(
                "Folder \'%s\' doesn't exist. Creating it.", folder)
            try:
                self.dbx.files_create_folder(folder)
                return False
            except Exception as ex:
                txt = "Exception of type {0}. Arguments:\n{1!r}"
                msg = txt.format(type(ex).__name__, ex.args)
                self.logger.error(msg)
                sys.exit(1)

    def count_of_files(self, folder):
        return len(self.remote_list(folder))

    def oldest_file(self, folder):
        files = []
        entries = self.remote_list(folder)
        for entry in entries:
            files.append(entry.name)
        files.sort()
        return files[0]

    def delete_file(self, f):
        try:
            self.dbx.files_delete(f)
        except Exception as err:
            self.logger.error("Couldn't delete the file: %s\n%s", f, err)

    def clean(self):
        if self.count_of_files(self.remote_folder) > self.max_files:
            file_to_delete = self.oldest_file(self.remote_folder)
            if file_to_delete.endswith(self.ext):
                file_path = os.path.normpath(
                    self.remote_folder + "/" + file_to_delete)
                self.logger.info("Deleting \'%s\'...", file_path)
                self.delete_file(file_path)
            else:
                self.logger.warning(
                    "Tried to delete the file \'%s\' but it doesn't appear to be a \'%s\' archive",
                    file_to_delete,
                    self.ext
                )

    @timer
    def upload_file(self, fname, dest):
        """ upload to dropbox
        fname = file to upload
        dest = destination path in dropbox including filename
        """
        dest = os.path.normpath(dest)
        fname = os.path.realpath(fname)
        file_size = os.path.getsize(fname)
        chunk_size = 32 * 1024 * 1024
        elapsed = 0
        if not self.check_space(file_size):
            fsize_mb = round(file_size / (1024*1024), 2)
            self.logger.error(
                "Not enough space in Dropbox to upload file of: %f MB", fsize_mb)
            os.remove(fname)
            sys.exit(1)

        self.logger.info("Uploading %s", fname)
        with open(fname, 'rb') as f:
            if file_size <= chunk_size:
                t0 = time()
                try:
                    res = self.dbx.files_upload(f.read(), dest, mute=True)
                    elapsed = by_chunk_info(
                        file_size, chunk_size, f.tell(), t0, elapsed)
                except dropbox.exceptions.ApiError as err:
                    self.logger.error("*** API error \n%s", str(err))
                    return None
            else:
                try:
                    t0 = time()
                    upload_session_start_result = self.dbx.files_upload_session_start(
                        f.read(chunk_size)
                    )
                    cursor = dropbox.files.UploadSessionCursor(
                        session_id=upload_session_start_result.session_id,
                        offset=f.tell(),
                    )
                    commit = dropbox.files.CommitInfo(path=dest)
                    elapsed = by_chunk_info(
                        file_size, chunk_size, f.tell(), t0, elapsed)
                    while f.tell() < file_size:
                        t0 = time()
                        if (file_size - f.tell()) <= chunk_size:
                            res = self.dbx.files_upload_session_finish(
                                f.read(chunk_size), cursor, commit
                            )
                        else:
                            self.dbx.files_upload_session_append(
                                f.read(chunk_size),
                                cursor.session_id,
                                cursor.offset,
                            )
                            cursor.offset = f.tell()
                        elapsed = by_chunk_info(
                            file_size, chunk_size, f.tell(), t0, elapsed)
                except dropbox.exceptions.ApiError as err:
                    self.logger.error("*** API error\n%s", err)
                    return None
        return res


@timer
def backup(dbx):
    logger = logging.getLogger(__name__)
    # tar
    curr_time = datetime.now().strftime("%Y%m%d%H%M%S")
    tar_name = curr_time + '.tar'
    tar_path = os.path.join(TMP_PATH, tar_name)
    create_tar(dbx.local_folder, tar_path)
    tar_md5 = md5(tar_path)

    # check if md5 exists in dropbox
    if dbx.file_exists(tar_md5, dbx.remote_folder):
        logger.info("Found md5 \"%s\" in Dropbox, no backup needed.", tar_md5)
        os.remove(tar_path)
    else:
        # it doesn't exists, compress, encrypt and upload
        compressed_name = compress(tar_path)
        encrypted_name = gpg_encrypt(compressed_name, dbx.userid, dbx.password)

        dbx.ext = '.' + encrypted_name.split(".", 1)[-1]
        new_name = curr_time + "-" + tar_md5 + dbx.ext
        new_name = os.path.join(TMP_PATH, new_name)
        os.rename(encrypted_name, new_name)

        logger.info("File %s not in Dropbox, uploading...", new_name)
        res = dbx.upload_file(
            new_name,
            os.path.normpath(dbx.remote_folder + "/" +
                             os.path.basename(new_name))
        )
        if res is not None:
            logger.info("File uploaded successfully to %s", res.path_display)
        else:
            logger.error("Failed to upload the file.")

        logger.info("Cleaning...")
        os.remove(new_name)
        dbx.clean()


@timer
def download(dbx):
    logger = logging.getLogger(__name__)
    # check if folder or files are selected
    try:
        md, res = dbx.dbx.files_download(dbx.to_download)
    except Exception as ex:
        txt = "Couldn't download file {0}.\nException of type {1}. Arguments:\n{2!r}"
        msg = txt.format(dbx.to_download, type(ex).__name__, ex.args)
        logger.error(msg)
        sys.exit(1)

    if md.is_downloadable:
        file_size = md.size
        elapsed = 0
        chunk_size = 32 * 1024 * 1024
        logger.info("Downloading: %s", md.name)
        try:
            with open(md.name, "wb") as f:
                # not using for data in res.iter_content(chunk_size) because I want to measure the time.
                while True:
                    t0 = time()
                    try:
                        data = next(res.iter_content(chunk_size))
                    except StopIteration:
                        break
                    f.write(data)
                    elapsed = by_chunk_info(
                        file_size, chunk_size, f.tell(), t0, elapsed)
        except Exception as ex:
            txt = "Exception writting file {0} to disk.\nException of type {1}. Arguments:\n{2!r}"
            msg = txt.format(md.name, type(ex).__name__, ex.args)
            logger.error(msg)
            os.remove(md.name)
    else:
        logger.info("File is not downloadable. (permissions?)")


@timer
def remote_list(dbx):
    logger = logging.getLogger(__name__)
    entries = dbx.remote_list(dbx.path)
    logger.info("*"*12 + " Listing results " + "*"*13 + '\n')
    for entry in entries:
        full_path = entry.path_display
        try:
            size = str(round(entry.size / (1024*1024), 2)) + 'MB'
        except:
            size = ""
        logger.info("%s  %s\n", full_path, size)
    logger.info("*"*42)


def init():
    if not os.path.isdir(TMP_PATH):
        os.mkdir(TMP_PATH)
    # Arguments
    parser = argparse.ArgumentParser(description='Dropbox manager')
    subparsers = parser.add_subparsers(dest='mode_option')
    subparsers.required = True
    bkp_p = subparsers.add_parser('backup', help='Backup to Dropbox.')
    bkp_p.add_argument('-r', '--remote-folder', nargs=1, required=True,
                       help='Destination folder at Dropbox')
    bkp_p.add_argument('-l', '--local-folder', nargs=1, required=True,
                       help='Local directory to backup')
    bkp_p.add_argument('-m', '--max-files', nargs=1, type=int, required=True,
                       help='Maximum number of backups to store (will delete oldest)')
    down_p = subparsers.add_parser(
        'download', help='Download file from Dropbox')
    down_p.add_argument('-f', '--file', nargs=1, required=True,
                        help='Location of the file to download from Dropbox')
    down_p = subparsers.add_parser('list', help='List contents from Dropbox.')
    down_p.add_argument('-f', '--file', nargs=1, required=True,
                        help='Folder/file path to list')
    args = parser.parse_args()

    # logger settings
    if not os.path.isdir(LOGS_PATH):
        os.mkdir(LOGS_PATH)
    logger = logging.getLogger(__name__)
    formatter = logging.Formatter('[%(asctime)s][%(levelname)s] %(message)s')
    if args.mode_option == 'backup':
        logname = 'dbx_cmd.py_' + args.remote_folder[0].split("/")[-1] + '.log'
        logpath = os.path.join(LOGS_PATH, logname)
        handler = RotatingFileHandler(logpath, maxBytes=102400, backupCount=2)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    # Config parser
    config = configparser.ConfigParser()
    try:
        config.read(SECRETS_CFG)
        dbxcfg = config['DBX']
        TOKEN = dbxcfg['TOKEN']
        if "USERID" in dbxcfg:
            USERID = dbxcfg['USERID']
            if len(USERID) == 0:
                USERID = None
        else:
            USERID = None
        if "PASSWORD" in dbxcfg:
            PASSWORD = dbxcfg['PASSWORD']
            if len(PASSWORD) == 0:
                PASSWORD = None
        else:
            PASSWORD = None
        if (USERID is None and PASSWORD is None):
            raise Exception(
                "Please define at least USERID(asymmetric) or PASSWORD(symmetric) in {0}".format(SECRETS_CFG))
    except Exception as ex:
        txt = "Exception of type {0}. Arguments:\n{1!r}"
        msg = txt.format(type(ex).__name__, ex.args)
        logger.error(msg)
        sys.exit(
            "Exception processing config vars, check {0}.".format(SECRETS_CFG))
    return args, (TOKEN, USERID, PASSWORD)


@timer
def main():
    # init config
    args, cfg = init()
    logger = logging.getLogger(__name__)
    # Startup
    logger.info("-"*30)
    logger.info("STARTING...")
    logger.info("-"*30)
    logger.info(repr(sys.argv))
    logger.info("-"*30)
    # init dropbox
    dbx = Dbx(args, cfg)
    # Check access token
    try:
        dbx.dbx.users_get_current_account()
    except AuthError:
        logger.error(
            "Invalid access token; try re-generating an access token for Dropbox.")
        sys.exit(1)

    if dbx.mode == 'backup':
        backup(dbx)
    elif dbx.mode == 'download':
        download(dbx)
    elif dbx.mode == 'list':
        remote_list(dbx)

    logger.info("-"*30)
    dbx.check_space()
    logger.info("END.")
    logger.info("-"*30)


if __name__ == '__main__':
    main()
