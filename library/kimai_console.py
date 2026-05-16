#!/usr/bin/python3
# -*- coding: utf-8 -*-

# (c) 2021-2026, Bodo Schulz <bodo@boone-schulz.de>
# Apache-2.0 (see LICENSE or https://opensource.org/license/apache-2-0)
# SPDX-License-Identifier: Apache-2.0

"""
Ansible module ``kimai_console`` – generic Kimai CLI dispatcher.

This module provides a thin, command-dispatching wrapper around the
Symfony ``bin/console`` binary shipped with Kimai.  It is intentionally
kept minimal; for richer parameter sets and proper per-entity idempotency
use the dedicated sibling modules ``kimai_install`` and ``kimai_user``
instead.

Supported commands
------------------
install
    Runs ``kimai:install``.  Idempotency is guaranteed via a local
    state-file (``state_install``).
user_create
    Runs ``kimai:user:create``.  Idempotency is guaranteed via a local
    state-file whose name is derived from the command string.

State-file caveat
-----------------
State-files are written to ``working_dir`` and persist across Ansible
runs.  They survive even if Kimai is later removed, which means a
reinstall on the same host requires manual deletion of the state-file.
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
module: kimai_console
version_added: "0.10.0"
author:
  - "Bodo Schulz (@bodsch) <me+ansible@bodsch.me>"

short_description: Generic wrapper around the Kimai bin/console CLI.

description:
  - Dispatches one of several Kimai Symfony-console sub-commands.
  - Idempotency is implemented via local state-files in C(working_dir).
  - For production use prefer the dedicated modules C(kimai_install) and
    C(kimai_user), which expose richer option sets.

options:
  command:
    description:
      - The Kimai console sub-command to execute.
      - C(install) maps to C(kimai:install).
      - C(user_create) maps to C(kimai:user:create).
    type: str
    default: install
    choices: [install, user_create]

  parameters:
    description:
      - Additional positional or flag arguments forwarded verbatim to the
        console command.  E.g. C(["--no-debug"]) or
        C(["admin", "admin@example.com", "ROLE_SUPER_ADMIN", "secret"]).
    type: list
    elements: str
    required: false
    default: []

  working_dir:
    description:
      - Absolute path to the Kimai installation directory.  The module
        expects C(bin/console) to exist inside this directory.
    type: str
    required: true

  environment:
    description:
      - Symfony environment name (currently informational only; pass
        C(--env) via C(parameters) to influence the console command).
    type: str
    required: false
    default: prod
"""

EXAMPLES = r"""
- name: Install Kimai
  kimai_console:
    command: install
    working_dir: /usr/share/kimai
    parameters:
      - "--no-debug"

- name: Create initial admin user
  kimai_console:
    command: user_create
    working_dir: /usr/share/kimai
    parameters:
      - "admin"
      - "admin@example.com"
      - "ROLE_SUPER_ADMIN"
      - "supersecret"
"""

RETURN = r"""
failed:
  description: Whether the module encountered an unrecoverable error.
  type: bool
  returned: always

changed:
  description: Whether a state change was performed on the target system.
  type: bool
  returned: always

msg:
  description: Human-readable description of the outcome.
  type: str
  returned: always
"""

# ---------------------------------------------------------------------------

# Pre-compiled pattern for parsing ``kimai:user:list`` tabular output.
#
# Expected line format (Kimai >= 2.x):
#   " admin      admin@example.com   ROLE_SUPER_ADMIN, ROLE_USER   Yes      kimai"
#
# Column notes:
#   - Username : word chars, dots, hyphens
#   - Email    : liberal practical set
#   - Roles    : comma-separated ROLE_* constants with optional spaces;
#                matched lazily so the "Yes|No" anchor stops the group
#   - Active   : literal "Yes" or "No" (replaces the old "X" marker)
#
# Separator lines ("--- --- ---") and the header line ("Username  Email …")
# never match because they lack a valid email token.

_USER_LIST_RE = re.compile(
    r"^\s+(?P<username>[\w.\-]+)"
    r"\s+(?P<email>[\w.+\-@]+)"
    r"\s+(?P<roles>[A-Z_,\s]+?)"
    r"\s+(?P<active>Yes|No)"
    r"\b",
    re.MULTILINE,
)


class KimaiConsole:
    """Ansible action class for dispatching Kimai console commands.

    The class is instantiated once per module invocation and is *not*
    intended to be reused across multiple runs.

    Attributes:
        module: The :class:`AnsibleModule` instance provided by Ansible.
        command: The sub-command to execute (``install`` or ``user_create``).
        parameters: Extra arguments forwarded to the console command.
        working_dir: Absolute path of the Kimai installation root.
        environment: Symfony environment identifier (informational).
    """

    module: AnsibleModule

    def __init__(self, module: AnsibleModule) -> None:
        """Initialise the dispatcher from Ansible module parameters.

        Args:
            module: Fully initialised :class:`AnsibleModule` instance.
        """
        self.module = module
        self.module.log("KimaiConsole::__init__()")

        self.command: str = module.params["command"]
        self.parameters: List[str] = module.params.get("parameters") or []
        self.working_dir: str = module.params["working_dir"]
        self.environment: str = module.params.get("environment", "prod")

        # Resolved at runtime inside :meth:`run`.
        self._console: str = ""

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> Dict[str, Any]:
        """Dispatch the requested sub-command and return the Ansible result dict.

        Returns:
            A dict with at least the keys ``failed``, ``changed``, and ``msg``.
        """
        self._console = os.path.join(self.working_dir, "bin", "console")

        if not os.path.exists(self._console):
            return dict(failed=True, changed=False, msg="missing bin/console")

        # self.module.log(msg=f" command   : '{self.command}'")
        # self.module.log(msg=f" parameters: '{self.parameters}'")
        os.chdir(self.working_dir)

        dispatch: Dict[str, Any] = {
            "install": self._kimai_install,
            "user_create": lambda: self._kimai_user(mode="user_create"),
        }

        handler = dispatch.get(self.command)
        if handler is None:
            return dict(
                failed=True,
                changed=False,
                msg=f"Unknown command: '{self.command}'",
            )

        return handler()

    # ------------------------------------------------------------------
    # Private command implementations
    # ------------------------------------------------------------------

    def _kimai_version(self) -> Tuple[bool, Optional[str]]:
        """Query the installed Kimai version via the console.

        Returns:
            A 2-tuple ``(success, version_string)``.  *version_string* is
            ``None`` when the version could not be parsed.
        """
        args = [self._console, "kimai:version", "--no-ansi"]

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

    def _kimai_install(self) -> Dict[str, Any]:
        """Execute ``kimai:install`` unless the state-file is present.

        Returns:
            Ansible result dict.
        """
        touch_file = f"state_{self.command}"

        if os.path.exists(touch_file):
            return dict(failed=False, changed=False, msg="kimai is already installed.")

        args = [self._console, "kimai:install"] + self.parameters

        # self.module.log(msg=f" args: '{args}'")
        rc, out, _ = self.__exec(args, check_rc=False)

        if rc == 0:
            Path(touch_file).touch()
            return dict(
                failed=False, changed=True, msg="kimai was successfully installed."
            )

        return dict(failed=True, changed=False, msg=out)

    def _kimai_user(self, mode: str = "user_create") -> Dict[str, Any]:
        """Execute ``kimai:user:create`` unless the state-file is present.

        The method first queries the existing user list so that the
        information is available in the module log; actual idempotency
        is controlled by the state-file.

        Args:
            mode: Currently only ``"user_create"`` is supported.

        Returns:
            Ansible result dict.
        """
        self.module.log(f"KimaiConsole::_kimai_user(mode: {mode})")

        created_users = self._kimai_list_users()
        self.module.log(msg=f"= created_users : '{created_users}'")

        touch_file = f"state_{self.command}"

        if os.path.exists(touch_file):
            return dict(failed=False, changed=False, msg="user is already installed.")

        args = [self._console, "kimai:user:create"] + self.parameters

        rc, out, _ = self.__exec(args, check_rc=False)

        if rc == 0:
            Path(touch_file).touch()
            return dict(
                failed=False,
                changed=True,
                msg=(
                    "user was successfully created."
                    if mode == "user_create"
                    else "command executed."
                ),
            )

        # rc != 0 → propagate failure; do *not* silence the error.
        return dict(failed=True, changed=False, msg=out)

    def _kimai_list_users(self) -> Dict[str, Any]:
        """Return a list of all registered Kimai usernames.

        Parses the tabular output of ``kimai:user:list``.

        Returns:
            A dict with keys ``failed`` (bool), ``changed`` (bool), and
            ``users`` (list of username strings).
        """
        self.module.log("KimaiConsole::_kimai_list_users()")

        args = [
            self._console,
            "kimai:user:list",
            "--no-interaction",
            "--no-ansi",
        ]

        rc, out, _ = self.__exec(args, check_rc=False)

        users: List[str] = []

        if rc == 0:
            for line in out.splitlines():
                self.module.log(msg=f"line: {line}")
                match = _USER_LIST_RE.search(line)
                if match:
                    users.append(match.group("username"))

        return dict(failed=(rc != 0), changed=False, users=users)

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
        command=dict(
            default="install",
            choices=["install", "user_create"],
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
            default="prod",
        ),
    )

    module = AnsibleModule(
        argument_spec=specs,
        supports_check_mode=False,
    )

    kc = KimaiConsole(module)
    result = kc.run()

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
