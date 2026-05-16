#!/usr/bin/python3
# -*- coding: utf-8 -*-

# (c) 2021-2026, Bodo Schulz <bodo@boone-schulz.de>
# Apache-2.0 (see LICENSE or https://opensource.org/license/apache-2-0)
# SPDX-License-Identifier: Apache-2.0

"""
Ansible module ``kimai_install`` – idempotent Kimai installation trigger.

This module wraps the ``kimai:install`` Symfony console command and ensures
the command is executed at most once per Kimai installation directory.
Idempotency is implemented by writing a local state-file (``state_install``)
into C(working_dir) upon successful installation.

State-file caveat
-----------------
The state-file persists across Ansible runs.  A reinstall on the same host
requires manual deletion of the file before the next playbook run.

Version detection
-----------------
The currently installed Kimai version is resolved via ``kimai:version``
and included in the idempotency message so operators can identify the
installed release at a glance.
"""

from __future__ import absolute_import, annotations, print_function

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ansible.module_utils.basic import AnsibleModule

# ---------------------------------------------------------------------------

DOCUMENTATION = r"""
---
module: kimai_install
version_added: "0.10.0"
author:
  - "Bodo Schulz (@bodsch) <me+ansible@bodsch.me>"

short_description: Idempotent wrapper around the Kimai C(kimai:install) command.

description:
  - Runs C(bin/console kimai:install) inside the Kimai installation directory.
  - Subsequent runs are skipped when the local state-file C(state_install)
    exists inside C(working_dir), ensuring idempotency.
  - The current Kimai version is detected before the install check and
    included in the skip message for operator visibility.

options:
  env:
    description:
      - Symfony environment name passed via C(--env) to the console command.
    type: str
    required: false
    default: prod

  parameters:
    description:
      - Additional arguments forwarded verbatim to C(kimai:install).
        Example: C(["--no-debug"]).
    type: list
    elements: str
    required: false
    default: []

  working_dir:
    description:
      - Absolute path to the Kimai installation root.  The module expects
        C(bin/console) to reside inside this directory.
    type: str
    required: true

  environment:
    description:
      - Ansible-level environment dictionary (passed through by Ansible;
        not forwarded to the Symfony console).
    type: dict
    required: false
"""

EXAMPLES = r"""
- name: Install Kimai (production)
  kimai_install:
    working_dir: /usr/share/kimai

- name: Install Kimai in staging environment
  kimai_install:
    working_dir: /usr/share/kimai
    env: staging
    parameters:
      - "--no-debug"
"""

RETURN = r"""
failed:
  description: Whether the module encountered an unrecoverable error.
  type: bool
  returned: always

changed:
  description: Whether C(kimai:install) was executed and succeeded.
  type: bool
  returned: always

msg:
  description: Human-readable description of the outcome.
  type: str
  returned: always
"""

# ---------------------------------------------------------------------------


class KimaiInstall:
    """Ansible action class for running ``kimai:install``.

    The class is instantiated once per module invocation and is *not*
    intended to be reused across multiple runs.

    Attributes:
        module: The :class:`AnsibleModule` instance provided by Ansible.
        env: Symfony environment name forwarded to ``--env``.
        parameters: Extra arguments forwarded to the console command.
        working_dir: Absolute path of the Kimai installation root.
    """

    module: AnsibleModule

    def __init__(self, module: AnsibleModule) -> None:
        """Initialise the installer from Ansible module parameters.

        Args:
            module: Fully initialised :class:`AnsibleModule` instance.
        """
        self.module = module
        self.module.log("KimaiInstall::__init__()")

        self.env: str = module.params.get("env") or "prod"
        self.parameters: List[str] = module.params.get("parameters") or []
        self.working_dir: str = module.params["working_dir"]

        # Resolved at runtime inside :meth:`run`.
        self._console: str = ""

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> Dict[str, Any]:
        """Validate the environment and trigger the install sequence.

        Returns:
            A dict with at least the keys ``failed``, ``changed``, and ``msg``.
        """
        self.module.log("KimaiInstall::run()")

        self._console = os.path.join(self.working_dir, "bin", "console")

        if not os.path.exists(self._console):
            return dict(failed=True, changed=False, msg="missing bin/console")

        # self.module.log(msg=f" parameters: '{self.parameters}'")

        os.chdir(self.working_dir)
        return self._kimai_install()

    # ------------------------------------------------------------------
    # Private command implementations
    # ------------------------------------------------------------------

    def _kimai_install(self) -> Dict[str, Any]:
        """Execute ``kimai:install`` unless the state-file already exists.

        The method first resolves the currently installed version so that
        the skip message is informative.  The actual installation is
        guarded by the ``state_install`` state-file.

        Returns:
            Ansible result dict.
        """
        self.module.log("KimaiInstall::_kimai_install()")

        _success, version = self._kimai_version()
        touch_file = "state_install"

        if os.path.exists(touch_file):
            version_info = f"version {version}" if version else "an unknown version"
            return dict(
                failed=False,
                changed=False,
                msg=f"kimai is already installed ({version_info}).",
            )

        args: List[str] = [
            self._console,
            "kimai:install",
            "--no-interaction",
            "--no-ansi",
            "--env",
            self.env,
        ]

        if self.parameters:
            args.extend(self.parameters)

        # self.module.log(msg=f" args: '{args}'")
        rc, out, _ = self.__exec(args, check_rc=False)

        if rc == 0:
            Path(touch_file).touch()
            return dict(
                failed=False, changed=True, msg="kimai was successfully installed."
            )

        return dict(failed=True, changed=False, msg=out)

    def _kimai_version(self) -> Tuple[bool, Optional[str]]:
        """Query the installed Kimai version via the console.

        Runs ``kimai:version --no-ansi`` and parses the version string
        from the expected output format::

            Kimai 2.x.y by Kevin Papst.

        Returns:
            A 2-tuple ``(success, version_string)``.  *version_string* is
            ``None`` when the version could not be determined.
        """
        self.module.log("KimaiInstall::_kimai_version()")

        args: List[str] = [self._console, "kimai:version", "--no-ansi"]

        # self.module.log(msg=f" args: '{args}'")
        rc, out, _ = self.__exec(args, check_rc=False)

        version_string: Optional[str] = None
        if rc == 0:
            pattern = re.compile(
                r"^Kimai (?P<version>\S+) by Kevin Papst\.$",
                re.MULTILINE,
            )
            match = pattern.search(out)
            if match:
                version_string = match.group("version")

        return (rc == 0, version_string)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def __exec(
        self,
        commands: List[str],
        check_rc: bool = True,
    ) -> Tuple[int, str, str]:
        """Run an external command via the Ansible module helper.

        Args:
            commands: Argv list to execute.
            check_rc: When ``True`` Ansible raises on non-zero exit codes.

        Returns:
            A 3-tuple ``(rc, stdout, stderr)``.
        """
        rc, out, err = self.module.run_command(commands, check_rc=check_rc)
        if rc != 0:
            self.module.log(msg=f"  out: '{out}'")
            self.module.log(msg=f"  err: '{err}'")
        return rc, out, err


# ---------------------------------------------------------------------------


def main() -> None:
    """Module entry point.  Called by Ansible at runtime."""
    specs: Dict[str, Any] = dict(
        env=dict(
            required=False,
            type="str",
            default="prod",
        ),
        parameters=dict(
            required=False,
            type="list",
            elements="str",
            default=[],
        ),
        working_dir=dict(
            required=True,
            type="str",
        ),
        environment=dict(
            required=False,
        ),
    )

    module = AnsibleModule(
        argument_spec=specs,
        supports_check_mode=False,
    )

    ki = KimaiInstall(module)
    result = ki.run()

    module.log(msg=f"= result : '{result}'")
    module.exit_json(**result)


if __name__ == "__main__":
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
