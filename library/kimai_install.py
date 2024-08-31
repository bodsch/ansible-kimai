#!/usr/bin/python3
# -*- coding: utf-8 -*-

# (c) 2021-2024, Bodo Schulz <bodo@boone-schulz.de>
# Apache-2.0 (see LICENSE or https://opensource.org/license/apache-2-0)
# SPDX-License-Identifier: Apache-2.0

from __future__ import absolute_import, print_function
import os
import re

from ansible.module_utils.basic import AnsibleModule


__metaclass__ = type

ANSIBLE_METADATA = {
    'metadata_version': '0.1',
    'status': ['preview'],
    'supported_by': 'community'
}


class KimaiConsole(object):
    """
    """
    module = None

    def __init__(self, module):
        """
        """
        self.module = module

        self.env = module.params.get("env")
        self.parameters = module.params.get("parameters")
        self.working_dir = module.params.get("working_dir")
        self.environment = module.params.get("environment")

    def run(self):
        """
        """
        # _failed = True
        # _changed = False
        # _msg = "initial message"

        self._console = os.path.join(self.working_dir, 'bin', 'console')

        self.module.log(msg=f" console   : '{self._console}'")

        if not os.path.exists(self._console):
            return dict(
                failed = True,
                changed = False,
                msg = "missing bin/console"
            )

        self.module.log(msg=f" parameters: '{self.parameters}'")

        os.chdir(self.working_dir)

        return self.kimai_install()

    def kimai_install(self):
        """
        """
        _failed = True
        _changed = False

        rc, version = self.kimai_version()

        touch_file = "state_install"

        if os.path.exists(touch_file):
            return dict(
                failed = False,
                changed = False,
                msg = f"kimai is already in version {version} installed."
            )

        args = []
        args.append(self._console)
        args.append("kimai:install")
        args.append("--no-interaction")
        args.append("--no-ansi")

        if self.env:
            args.append("--env")
            args.append(self.env)

        if self.parameters and len(self.parameters) > 0:
            args += self.parameters

        self.module.log(msg=f" args: '{args}'")

        rc, out, err = self.__exec(args, check_rc=False)

        if rc == 0:
            from pathlib import Path
            Path(touch_file).touch()

            _failed = False
            _changed = True

            _msg = "kimai was successfully installed."

        else:
            _msg = out

        return dict(
            failed=_failed,
            changed=_changed,
            msg=_msg
        )

    def kimai_version(self):
        """
        """
        version_string = None

        args = []
        args.append(self._console)
        args.append("kimai:version")
        args.append("--no-ansi")

        self.module.log(msg=f" args: '{args}'")

        rc, out, err = self.__exec(args, check_rc=False)

        if rc == 0:
            pattern = re.compile(r"^Kimai (?P<version>.*) by Kevin Papst.$", re.MULTILINE)
            version = re.search(pattern, out)
            if version:
                version_string = version.group('version')

        return (rc == 0, version_string)

    def __exec(self, commands, check_rc=True):
        """
          execute shell program
        """
        rc, out, err = self.module.run_command(commands, check_rc=check_rc)
        if rc != 0:
            self.module.log(msg=f"  out: '{out}'")
            self.module.log(msg=f"  err: '{err}'")

        return rc, out, err


def main():
    """
    """
    specs = dict(
        env=dict(
            required=False,
            type=str,
            default="prod"
        ),
        parameters=dict(
            required=False,
            type=list,
            default=[]
        ),
        working_dir=dict(
            required=True,
            type=str
        ),
        environment=dict(
            required=False,
        )
    )

    module = AnsibleModule(
        argument_spec=specs,
        supports_check_mode=False,
    )

    kc = KimaiConsole(module)
    result = kc.run()

    module.log(msg=f"= result : '{result}'")

    module.exit_json(**result)


# import module snippets
if __name__ == '__main__':
    main()


"""
root@instance:/usr/share/kimai-2.0.29# bin/console --help
Description:
  List commands

Usage:
  list [options] [--] [<namespace>]

Arguments:
  namespace             The namespace name

Options:
      --raw             To output raw command list
      --format=FORMAT   The output format (txt, xml, json, or md) [default: "txt"]
      --short           To skip describing commands' arguments
  -h, --help            Display help for the given command. When no command is given display help for the list command
  -q, --quiet           Do not output any message
  -V, --version         Display this application version
      --ansi|--no-ansi  Force (or disable --no-ansi) ANSI output
  -n, --no-interaction  Do not ask any interactive question
  -e, --env=ENV         The Environment name. [default: "prod"]
      --no-debug        Switch off debug mode.
  -v|vv|vvv, --verbose  Increase the verbosity of messages: 1 for normal output, 2 for more verbose output and 3 for debug

Help:
  The list command lists all commands:

    bin/console list

  You can also display the commands for a specific namespace:

    bin/console list test

  You can also output the information in other formats by using the --format option:

    bin/console list --format=xml

  It's also possible to get raw list of commands (useful for embedding command runner):

    bin/console list --raw
"""
