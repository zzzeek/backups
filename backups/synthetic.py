#!/usr/bin/python

import boto
from . import base
import argparse
import re
import functools
from multiprocessing import Pool
import tempfile


def duplicity_cmd(cmd_options, replace_dict, *args):

    cmd_options = list(cmd_options)
    cmd_options.append(args[0])
    cmd_options.extend([a % replace_dict for a in args[1:]])

    base._run_duplicity(None, cmd_options, False, False)

def log(msg, *args):
    print msg % args

def _copy_key(arg):
    source_name, keyname, dest_name = arg
    source_bucket = s3.lookup(source_name)
    key = source_bucket.get_key(keyname)
    log("Copying %s", key.key)
    key.copy(dest_name, key.key)

def _global_connect(config_dict):
    global s3
    base._render_env_args(config_dict)
    s3 = boto.connect_s3()

def _copy_bucket(copy_pool, source_bucket, dest_bucket_name):
    copy_pool.map(_copy_key, [
                (source_bucket.name, key.key, dest_bucket_name)
                for key in source_bucket.list()
            ])

def run_synthetic(config, args):
    config_dict = base._get_config(config, args)
    copy_pool = Pool(10, _global_connect, (config_dict, ))

    cmd_options = []
    base._setup_command(cmd_options, config_dict)
    base._render_options_args(config_dict, cmd_options)

    target_url = config_dict['target_url']

    source_bucket_name = re.match(r"s3\+http:\/\/(.+)",
                                        target_url).group(1)

    tmp_source = "tmp_source_%s" % source_bucket_name
    tmp_dest = "tmp_dest_%s" % source_bucket_name

    replace_dict = {"source_bucket_name": source_bucket_name,
                    "tmp_source": tmp_source,
                    "tmp_dest": tmp_dest
                    }
    run_duplicity_cmd = functools.partial(
                                duplicity_cmd, cmd_options, replace_dict)

    s3 = boto.connect_s3()

    # create temp buckets, dir
    local_tmp_dir = tempfile.mkdtemp()
    tmp_source_bucket = s3.create_bucket(tmp_source)
    tmp_dest_bucket = s3.create_bucket(tmp_dest)

    try:
        source_bucket = s3.lookup(source_bucket_name)

        all_source_keys = set(k.key for k in source_bucket.list())

        # copy everything in original source bucket to temp source
        _copy_bucket(copy_pool, source_bucket, tmp_source)

        # restore from temp source
        log("Restoring from %s to %s", tmp_source, local_tmp_dir)
        run_duplicity_cmd("restore", "s3+http://%(tmp_source)s", local_tmp_dir)

        # do a full backup to temp dest
        log("Backing up full from %s to %s", local_tmp_dir, tmp_dest)
        run_duplicity_cmd("full", local_tmp_dir, "s3+http://%(tmp_dest)s")

        # check for keys added
        new_source_keys = set(k.key for k in source_bucket.list())

        diff = new_source_keys.difference(all_source_keys)
        if diff:
            raise Exception(
                        "New files have been added to %s since "
                        "synthetic compression started: %r" % (
                                source_bucket_name,
                                diff
                            )
                    )

        # copy everything from temp dest back to original source
        _copy_bucket(copy_pool, tmp_dest_bucket, source_bucket_name)

        # do an everythign-but-n whatever for original source

    finally:
        # 8. remove tmp buckets
        tmp_source_bucket.delete_keys(tmp_source_bucket.list())
        tmp_source_bucket.delete()
        tmp_dest_bucket.delete_keys(tmp_dest_bucket.list())
        tmp_dest_bucket.delete()
        shutil.rmtree(local_tmp_dir)


def main(argv=None, **kwargs):
    parser = argparse.ArgumentParser(prog="synthetic_backup")
    parser.add_argument("configuration", type=str,
                help="name of configuration to load")

    args = parser.parse_args(argv)
    config = base._read_config()

    run_synthetic(config, args)


if __name__ == '__main__':
    main()
