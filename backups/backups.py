import argparse
from . import base
import functools
import sys


def _global_options(subparser):
    subparser.add_argument(
        "configuration", type=str,
        help="name of configuration to load")
    subparser.add_argument(
        "-d", "--dry", action="store_true",
        help="Only show the final "
        "duplicity command, don't actually run it")


def main(argv=None, **kwargs):

    dupl_commands = set([
        "verify", "collection-status",
        "list-current-files",
        "remove-older-than", "cleanup",
        "remove-all-but-n-full"])
    force_commands = set([
        "remove-older-than",
        "cleanup",
        "remove-all-but-n-full"])
    one_arg_commands = set(["remove-older-than", "remove-all-but-n-full"])

    parser = argparse.ArgumentParser(prog="backups")
    subparsers = parser.add_subparsers(help="sub-command help")
    for name in dupl_commands:
        subparser = subparsers.add_parser(
            name,
            help="run the duplicity command %r" % name)
        subparser.set_defaults(cmd=functools.partial(base._dupl_command, name))
        if name in one_arg_commands:
            subparser.add_argument("arg", type=str, help="command argument")
        _global_options(subparser)
        if name in force_commands:
            subparser.add_argument("--force", action="store_true",
                                   help="duplicity --force option")

    subparser = subparsers.add_parser("restore", help="run a restore")
    _global_options(subparser)
    subparser.add_argument("dest", help="Path or file to restore, "
                           "passed to --file-to-restore")
    subparser.add_argument("--restore-to-path", help="put files in this base")
    subparser.set_defaults(cmd=base._restore)

    subparser = subparsers.add_parser("full", help="run a full backup")
    subparser.set_defaults(cmd=functools.partial(base._backup, "full"))
    subparser.add_argument("--asynchronous-upload", action="store_true",
                           help="use async mode")
    _global_options(subparser)

    subparser = subparsers.add_parser(
        "incremental",
        help="run an incremental backup")
    subparser.set_defaults(cmd=functools.partial(base._backup, "incremental"))
    subparser.add_argument(
        "--asynchronous-upload", action="store_true",
        help="use async mode")
    _global_options(subparser)

    subparser = subparsers.add_parser("configs", help="list configs")
    subparser.set_defaults(cmd=base._list_configs)

    subparser = subparsers.add_parser("init", help="write sample config file")
    subparser.set_defaults(cmd=base._write_sample_config)

    args = parser.parse_args(argv)

    cmd_options = []

    cmd = args.cmd
    config = base._read_config()
    config_dict = base._get_config(config, args)
    base._render_env_args(config_dict)

    try:
        if config is None and cmd is not base._write_sample_config:
            raise base.CommandException(
                "No config file: %r.  "
                "Please run the 'init' command to create." %
                base.config_file_dest)

        cmd(config, cmd_options, args)
    except base.CommandException as ce:
        sys.exit(str(ce))

if __name__ == '__main__':
    main()
