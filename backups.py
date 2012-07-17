#!/usr/local/bin/python

import os
import ConfigParser
import re
import subprocess
import resource
import argparse
import functools
import sys
import errno

config_file_dest = os.path.join(
        os.environ['HOME'],
        ".duplicity",
        "backup.ini"
    )

lock_file_dest = os.path.join(
        os.environ['HOME'],
        ".duplicity"
    )

class CommandException(Exception):
    pass

def _is_uppercase(text):
    return text == text.upper()

def _setup_command(cmd_options, config_dict):
    cmd_options.append(config_dict['cmd'])

def _dupl_command(cmd, config, cmd_options, args):
    config_dict = _get_config(config, args)
    lock = cmd in ("remove-older-than",
                    "cleanup", "remove-all-but-n-full")

    _setup_command(cmd_options, config_dict)
    cmd_options.append(cmd)
    if getattr(args, 'force', False):
        cmd_options.append("--force")
    _render_options_args(config_dict, cmd_options)

    cmd_options.append(config_dict['target_url'])
    _run_duplicity(args.configuration, cmd_options, lock, args.dry)

def _lock(lock_file):
    try:
        os.mkdir(lock_file)
        return True
    except OSError, err:
        if err.errno == errno.EEXIST:
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

    path, fname = os.path.split(dest)
    if os.path.exists(os.path.join(os.sep, dest)):
        if not fname:
            path = path + ".restored"
        else:
            fname = fname + ".restored"

    cmd_options.extend(["--file-to-restore", dest])
    cmd_options.append(config_dict['target_url'])
    cmd_options.append(os.path.join(os.sep, path, fname))
    _run_duplicity(args.configuration, cmd_options, False, args.dry)

def _backup(cmd, config, cmd_options, args):
    config_dict = _get_config(config, args)
    _setup_command(cmd_options, config_dict)
    cmd_options.append(cmd)

    _render_options_args(config_dict, cmd_options)

    for src_opt in re.split(r'\\', config_dict['source']):
        src_opt = src_opt.strip()
        if not src_opt:
            continue
        name, opt = re.split(r'\s+', src_opt, 1)
        if "\n" in opt:
            raise SystemError(
                    "WARNING: newline detected in non-slashed "
                    "line \"%s\"; please double check your config file"
                    % opt.replace('\n', r'\n'))
        cmd_options.extend((name, opt))

    cmd_options.append("/")
    cmd_options.append(config_dict['target_url'])
    _run_duplicity(args.configuration, cmd_options, True, args.dry)

def _list_configs(config, cmd_options, args):
    print ("\n".join(config.sections()))
    return False

def _get_config(config, args):
    if not config.has_section(args.configuration):
        raise SystemError("no such config: %s" % args.configuration)

    return dict(config.items(args.configuration))

def _render_options_args(config_dict, cmd_options):
    dupl_opts = set(["v", "archive-dir", "name", "s3-use-new-style"])
    for k, v in config_dict.items():
        if _is_uppercase(k):
            os.environ[k] = v % (os.environ)
        elif k in dupl_opts:
            if k == 'v':
                cmd_options.append("-%s%s" % (k, v))
            elif v == 'true':
                cmd_options.append("--%s" % (k, ))
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
            "Config file %s already exists" % config_file_dest)
    with open(config_file_dest, 'w') as f:
        f.write(sample)
    print("Wrote config to %s" % config_file_dest)
    return False


def _global_options(subparser):
    subparser.add_argument("configuration", type=str,
                help="name of configuration to load")
    subparser.add_argument("-d", "--dry", action="store_true",
                help="Only show the final "
                "duplicity command, don't actually run it")

def _run_duplicity(name, cmd_options, lock, dry):
    print(" ".join(cmd_options))

    if not dry:
        def setlimits():
            resource.setrlimit(resource.RLIMIT_NOFILE, (1024, 1024))

        def proc():
            p = subprocess.Popen(cmd_options, preexec_fn=setlimits)
            p.wait()
        if lock:
            lockfile = os.path.join(lock_file_dest, "%s.lock" % name)
            if not _lock(lockfile):
                sys.stderr.write(
                    "Lockfile %s is already acquired\n" % lockfile)
                return
            try:
                proc()
            finally:
                _unlock(lockfile)
        else:
            proc()

def main(argv=None, **kwargs):

    dupl_commands = set(["verify", "collection-status",
            "list-current-files",
            "remove-older-than", "cleanup",
            "remove-all-but-n-full"])
    force_commands = set(["remove-older-than",
                        "cleanup",
                        "remove-all-but-n-full"])


    parser = argparse.ArgumentParser(prog="backups")
    subparsers = parser.add_subparsers(help="sub-command help")
    for name in dupl_commands:
        subparser = subparsers.add_parser(
                            name,
                            help="run the duplicity command %r" % name)
        subparser.set_defaults(cmd=functools.partial(_dupl_command, name))
        _global_options(subparser)
        if name in force_commands:
            subparser.add_argument("--force", action="store_true",
                        help="duplicity --force option")

    subparser = subparsers.add_parser("restore", help="run a restore")
    _global_options(subparser)
    subparser.add_argument("dest", help="Path or file to restore, "
                        "passed to --file-to-restore")
    subparser.set_defaults(cmd=_restore)

    subparser = subparsers.add_parser("full", help="run a full backup")
    subparser.set_defaults(cmd=functools.partial(_backup, "full"))
    _global_options(subparser)

    subparser = subparsers.add_parser("incremental",
                            help="run an incremental backup")
    subparser.set_defaults(cmd=functools.partial(_backup, "incremental"))
    _global_options(subparser)

    subparser = subparsers.add_parser("configs", help="list configs")
    subparser.set_defaults(cmd=_list_configs)

    subparser = subparsers.add_parser("init", help="write sample config file")
    subparser.set_defaults(cmd=_write_sample_config)

    args = parser.parse_args(argv)

    cmd_options = []

    cmd = args.cmd

    try:
        config = ConfigParser.SafeConfigParser()
        config.optionxform = str
        if not os.path.exists(config_file_dest):
            if cmd is not _write_sample_config:
                raise CommandException("No config file: %r.  "
                    "Please run the 'init' command to create." %
                    config_file_dest)
        else:
            config.read(config_file_dest)


        cmd(config, cmd_options, args)
    except CommandException, ce:
        sys.exit(str(ce))

if __name__ == '__main__':
    main()
