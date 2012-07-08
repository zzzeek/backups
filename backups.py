#!/usr/local/bin/python

import os
import ConfigParser
import re
import subprocess
import resource
import argparse
import functools
import sys

config_file_dest = os.path.join(
        os.environ['HOME'],
        ".duplicity",
        "backup.ini"
    )

class CommandException(Exception):
    pass

def _is_uppercase(text):
    return text == text.upper()

def _dupl_command(cmd, config, cmd_options, args):
    config_dict = _get_config(config, args)
    cmd_options.append(config_dict['cmd'])
    cmd_options.append(cmd)
    if getattr(args, 'force', False):
        cmd_options.append("--force")
    _render_options_args(config_dict, cmd_options)
    cmd_options.extend(args.args)
    cmd_options.append(config_dict['target_url'])
    return True

def _backup(config, cmd_options, args):
    config_dict = _get_config(config, args)
    cmd_options.append(config_dict['cmd'])
    if args.type != 'auto':
        cmd_options.append(args.type)

    _render_options_args(config_dict, cmd_options)

    for src_opt in re.split(r'\\', config_dict['source']):
        src_opt = src_opt.strip()
        if not src_opt:
            continue
        name, opt = re.split(r'\s+', src_opt, 1)
        cmd_options.extend((name, opt))

    cmd_options.append("/")
    cmd_options.append(config_dict['target_url'])
    return True

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
            os.environ[k] = v
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

# environment variables - all UPPERCASE
# names are sent to the env
AWS_ACCESS_KEY_ID=<your access key>
AWS_SECRET_ACCESS_KEY=<your secret key>
PASSPHRASE=this is my passphrase

# duplicity options
archive-dir=/Users/myusername/.duplicity/cache
v=8

# path of duplicity executable
cmd=/usr/local/bin/duplicity

# lockrun command - can be used in crons
# to limit number of duplicity calls to one
lockrun=/usr/local/bin/lockrun --quiet --lockfile=/var/log/duplicity/cron.lock --

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


def main(argv=None, **kwargs):

    dupl_commands = set(["verify", "collection-status",
            "list-current-files",
            "restore", "remove-older-than", "cleanup",
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
        subparser.add_argument("configuration", type=str,
                    help="name of configuration to load")
        subparser.set_defaults(cmd=functools.partial(_dupl_command, name))
        if name in force_commands:
            subparser.add_argument("--force", action="store_true",
                        help="duplicity --force option")
        subparser.add_argument("-d", "--dry", action="store_true",
                    help="Only show the final "
                    "duplicity command, don't actually run it")
        subparser.add_argument('args',
                        nargs=argparse.REMAINDER,
                        help="additional arguments are "
                        "passed to duplicity following the command.")
    subparser = subparsers.add_parser(
            "backup",
            help="run a backup",
        )
    subparser.set_defaults(cmd=_backup)
    subparser.add_argument("type",
                choices=("full", "incremental", "auto"),
                help="full or incremental backup")
    subparser.add_argument("-d", "--dry", action="store_true",
                    help="Only show the final "
                    "duplicity command, don't actually run it")
    subparser.add_argument("configuration", type=str,
                help="name of configuration to load")
    subparser = subparsers.add_parser(
            "configs",
            help="list configs"
        )
    subparser.set_defaults(cmd=_list_configs)
    subparser = subparsers.add_parser("init",
            help="write sample config file")
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

        if cmd(config, cmd_options, args):
            print(" ".join(cmd_options))

            if not args.dry:
                def setlimits():
                    resource.setrlimit(resource.RLIMIT_NOFILE, (1024, 1024))

                p = subprocess.Popen(cmd_options, preexec_fn=setlimits)
                p.wait()
    except CommandException, ce:
        sys.exit(str(ce))

if __name__ == '__main__':
    main()
