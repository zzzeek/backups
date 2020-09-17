#!/usr/local/bin/python

import os

try:
    import ConfigParser
except ImportError:
    import configparser as ConfigParser

import re
import subprocess
import resource
import sys
import errno
import time

config_file_dest = os.path.join(os.environ["HOME"], ".duplicity", "backup.ini")

lock_file_dest = os.path.join(os.environ["HOME"], ".duplicity")


class CommandException(Exception):
    pass


def _is_uppercase(text):
    return text == text.upper()


def _setup_command(cmd_options, config_dict):
    cmd_options.append(config_dict["cmd"])


def _dupl_command(cmd, config, cmd_options, args):
    config_dict = _get_config(config, args)
    lock = cmd in ("remove-older-than", "cleanup", "remove-all-but-n-full")

    _setup_command(cmd_options, config_dict)
    cmd_options.append(cmd)
    if getattr(args, "arg", None):
        cmd_options.append(args.arg)
    if getattr(args, "force", False):
        cmd_options.append("--force")
    _render_options_args(config_dict, cmd_options)

    cmd_options.append(config_dict["target_url"])
    _run_duplicity(args.configuration, cmd_options, lock, args.dry, config)


def _lock(lock_file, exists_callback=None):
    try:
        os.mkdir(lock_file)
        return True
    except OSError as err:
        if err.errno == errno.EEXIST:
            if exists_callback:
                return exists_callback()
            else:
                return False
        else:
            raise


def _unlock(lock_file):
    os.rmdir(lock_file)


def _restore(config, cmd_options, args):
    config_dict = _get_config(config, args)
    _setup_command(cmd_options, config_dict)
    cmd_options.append("restore")
    _render_options_args(config_dict, cmd_options)

    dest = os.path.normpath(args.dest)
    if dest.startswith(os.sep):
        dest = dest[1:]

    if args.restore_to_path:
        restore_to = args.restore_to_path
    else:
        path, fname = os.path.split(dest)
        if os.path.exists(os.path.join(os.sep, dest)):
            if not fname:
                path = path + ".restored"
            else:
                fname = fname + ".restored"
        restore_to = os.path.join(os.sep, path, fname)

    if dest:
        cmd_options.extend(["--file-to-restore", dest])
    if args.restore_to_path:
        cmd_options.extend(["--numeric-owner", "--force"])
    cmd_options.append(config_dict["target_url"])
    cmd_options.append(restore_to)
    _run_duplicity(args.configuration, cmd_options, False, args.dry, config)


def _backup(cmd, config, cmd_options, args):
    config_dict = _get_config(config, args)
    _setup_command(cmd_options, config_dict)
    cmd_options.append(cmd)

    if args.asynchronous_upload:
        cmd_options.append("--asynchronous-upload")

    _render_options_args(config_dict, cmd_options)

    for src_opt in re.split(r"\\", config_dict["source"]):
        src_opt = src_opt.strip()
        if not src_opt:
            continue
        name, opt = re.split(r"\s+", src_opt, 1)
        if "\n" in opt:
            raise SystemError(
                "WARNING: newline detected in non-slashed "
                'line "%s"; please double check your config file'
                % opt.replace("\n", r"\n")
            )
        cmd_options.extend((name, opt))

    cmd_options.append("/")
    cmd_options.append(config_dict["target_url"])
    _run_duplicity(args.configuration, cmd_options, True, args.dry, config)


def _list_configs(config, cmd_options, args):
    print("\n".join(config.sections()))
    return False


# TODO: cleanup these three
def _get_config(config, args):
    if not config.has_section(args.configuration):
        raise SystemError("no such config: %s" % args.configuration)

    return dict(config.items(args.configuration))


def _env_from_config(name, config):
    config_dict = dict(config.items(name))
    return dict((k, v) for k, v in config_dict.items() if _is_uppercase(k))


def _render_env_args(config_dict):
    for k, v in config_dict.items():
        if _is_uppercase(k):
            os.environ[k] = v % (os.environ)


def _render_options_args(config_dict, cmd_options):
    dupl_opts = set(
        [
            "v",
            "archive-dir",
            "name",
            "s3-use-new-style",
            "allow-source-mismatch",
            "tempdir",
            "asynchronous-upload",
            "timeout",
            "volsize",
            "ssh-options",
            "rsync-options",
            "ssh-askpass",
        ]
    )
    for k, v in config_dict.items():
        if _is_uppercase(k):
            os.environ[k] = v % (os.environ)
        elif k in dupl_opts:
            if k == "v":
                cmd_options.append("-%s%s" % (k, v))
            elif v == "true":
                cmd_options.append("--%s" % (k,))
            else:
                cmd_options.append("--%s=%s" % (k, v))


def _write_sample_config(config, cmd_options, args):
    sample = """
[DEFAULT]
# Arguments in the DEFAULT sections
# are passed to all sub-configs.
# Any argument here including environment
# variables can be per-sub-config.
# Values can have spaces, don't add quotes as these
# become part of the value.

# environment variables - all UPPERCASE
# names are sent to the env.
AWS_ACCESS_KEY_ID=<your access key>
AWS_SECRET_ACCESS_KEY=<your secret key>
PASSPHRASE=this is my passphrase

# env substitutions can also be used
# with UPPERCASE variables.  Use two
# percent signs, %%(varname)s
PATH=/usr/local/bin:%%(PATH)s

# duplicity options
archive-dir=/Users/myusername/.duplicity/cache
v=8

# path of duplicity executable
cmd=/usr/local/bin/duplicity

# each backup config is defined here,
# in its own [section].
[my_backup]

# duplicity "name" field
name=my_backup

# sources.  we always make the "desination"
# the root "/".   Fill in each desired directory
# here, keeping the one include/exclude per line with
# backslash/newline convention in place
source=\\
    --exclude /**/*.pyc \\
    --exclude /**.DS_Store \\
    --exclude /Users/myusername/.duplicity/cache \\
    --include /Users/myusername/Documents \\
    --include /Users/myusername/Desktop \\
    --exclude **

# target url.
target_url=file:///Volumes/WD Passport/duplicity/

"""
    if os.path.exists(config_file_dest):
        raise CommandException(
            "Config file %s already exists" % config_file_dest
        )
    with open(config_file_dest, "w") as f:
        f.write(sample)
    print("Wrote config to %s" % config_file_dest)
    return False


def _run_duplicity(name, cmd_options, lock, dry, config):
    print(" ".join(cmd_options))

    env = _env_from_config(name, config)

    for k in "SSH_AGENT_PID", "SSH_AUTH_SOCK":
        if k in os.environ:
            env[k] = os.environ[k]

    if not dry:

        def setlimits():
            resource.setrlimit(resource.RLIMIT_NOFILE, (1024, 1024))

        def proc():
            p = subprocess.Popen(cmd_options, preexec_fn=setlimits, env=env)
            p.wait()

        if lock:
            lockfile = os.path.join(lock_file_dest, "%s.lock" % name)

            def delete_old_lockfile():
                mtime = os.stat(lockfile).st_mtime
                age = time.time() - mtime
                if age > 10800:
                    sys.stderr.write(
                        "Lockfile %s is acquired, but is %d "
                        "seconds old, deleting" % (lockfile, age)
                    )
                    _unlock(lockfile)
                    return _lock(lockfile)
                else:
                    sys.stderr.write(
                        "Lockfile %s is already acquired, age: %d seconds\n"
                        % (lockfile, age)
                    )
                    return False

            if _lock(lockfile, delete_old_lockfile):
                try:
                    proc()
                finally:
                    _unlock(lockfile)
        else:
            proc()


def _read_config():
    config = ConfigParser.SafeConfigParser()
    config.optionxform = str
    if not os.path.exists(config_file_dest):
        return None
    else:
        config.read(config_file_dest)
    return config
