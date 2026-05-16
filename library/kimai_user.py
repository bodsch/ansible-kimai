#!/usr/bin/python3
# -*- coding: utf-8 -*-

# (c) 2022-2026, Bodo Schulz <bodo@boone-schulz.de>
# Apache-2.0 (see LICENSE or https://opensource.org/license/apache-2-0)
# SPDX-License-Identifier: Apache-2.0

"""
Ansible module ``kimai_user`` – full lifecycle management of Kimai users.

This module wraps the ``kimai:user:*`` family of Symfony console commands
and exposes them through a single, state-driven Ansible interface.

Supported states
----------------
create
    Creates a new user.  Skipped (idempotent) when the username already
    exists in ``kimai:user:list`` output.
activate
    Activates an existing user account.
deactivate
    Deactivates an existing user account.
promote
    Grants one or more roles to an existing user.  Each role in C(roles)
    results in a separate ``kimai:user:promote`` invocation.
demote
    Revokes one or more roles from an existing user.  Each role in
    C(roles) results in a separate ``kimai:user:demote`` invocation.

Role constants
--------------
The following role identifiers are accepted by Kimai:

* ``ROLE_USER``
* ``ROLE_TEAMLEAD``
* ``ROLE_ADMIN``
* ``ROLE_SUPER_ADMIN``
"""

from __future__ import absolute_import, annotations, print_function

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from ansible.module_utils.basic import AnsibleModule

# ---------------------------------------------------------------------------

DOCUMENTATION = r"""
---
module: kimai_user
version_added: "0.10.0"
author:
  - "Bodo Schulz (@bodsch) <me+ansible@bodsch.me>"

short_description: Manage Kimai user accounts via the Symfony console.

description:
  - Creates, activates, deactivates, promotes, and demotes Kimai users by
    delegating to the C(kimai:user:*) console commands.
  - The C(create) state checks C(kimai:user:list) before executing, making
    it safe to run repeatedly.
  - The C(promote) and C(demote) states call the console once per role so
    that partial role lists are applied atomically.

options:
  state:
    description:
      - Desired state of the user account.
    type: str
    default: create
    choices: [create, activate, deactivate, promote, demote]

  username:
    description:
      - Kimai username (must be unique within the installation).
    type: str
    required: true

  password:
    description:
      - Password for the user.  Required when C(state=create).
    type: str
    required: false
    no_log: true

  email:
    description:
      - E-mail address of the user.  Required when C(state=create).
    type: str
    required: false

  roles:
    description:
      - List of Kimai roles to assign (C(state=create)), promote to
        (C(state=promote)), or demote from (C(state=demote)).
      - Valid values are C(ROLE_USER), C(ROLE_TEAMLEAD), C(ROLE_ADMIN),
        and C(ROLE_SUPER_ADMIN).
      - Unknown role identifiers are silently filtered out.
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
- name: Create an admin user
  kimai_user:
    state: create
    working_dir: /usr/share/kimai
    username: admin
    email: admin@example.com
    password: "V3ryS3cur3!"
    roles:
      - ROLE_SUPER_ADMIN

- name: Deactivate a user
  kimai_user:
    state: deactivate
    working_dir: /usr/share/kimai
    username: john

- name: Promote a user to team lead
  kimai_user:
    state: promote
    working_dir: /usr/share/kimai
    username: john
    roles:
      - ROLE_TEAMLEAD

- name: Demote a user from admin
  kimai_user:
    state: demote
    working_dir: /usr/share/kimai
    username: john
    roles:
      - ROLE_ADMIN
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

# Valid Kimai role identifiers, in ascending privilege order.
_VALID_ROLES: Tuple[str, ...] = (
    "ROLE_USER",
    "ROLE_TEAMLEAD",
    "ROLE_ADMIN",
    "ROLE_SUPER_ADMIN",
)

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


class KimaiUser:
    """Ansible action class for managing Kimai user accounts.

    Each public ``kimai_*`` method corresponds to one ``state`` value and
    is selected by :meth:`run`.  Private helpers are prefixed with a single
    underscore; the execution helper uses Python name-mangling (``__exec``)
    to prevent accidental shadowing in potential sub-classes.

    Attributes:
        module: The :class:`AnsibleModule` instance provided by Ansible.
        state: Desired user state (``create``, ``activate``, …).
        working_dir: Absolute path of the Kimai installation root.
        environment: Symfony environment identifier (informational).
        username: Target Kimai username.
        password: Plaintext password (only needed for ``create``).
        email: E-mail address (only needed for ``create``).
        roles: List of role identifiers (used by ``create``, ``promote``,
               ``demote``).
    """

    module: AnsibleModule

    def __init__(self, module: AnsibleModule) -> None:
        """Initialise the user manager from Ansible module parameters.

        Args:
            module: Fully initialised :class:`AnsibleModule` instance.
        """
        self.module = module
        self.module.log("KimaiUser::__init__()")

        self.state: str = module.params["state"]
        self.working_dir: str = module.params["working_dir"]
        self.environment: str = module.params.get("environment") or "prod"
        self.username: str = module.params["username"]
        self.password: Optional[str] = module.params.get("password")
        self.email: Optional[str] = module.params.get("email")
        self.roles: List[str] = module.params.get("roles") or []

        # Resolved at runtime inside :meth:`run`.
        self._console: str = ""

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> Dict[str, Any]:
        """Dispatch the requested state handler and return the Ansible result.

        Returns:
            A dict with at least the keys ``failed``, ``changed``, and ``msg``.
        """
        self.module.log("KimaiUser::run()")

        self._console = os.path.join(self.working_dir, "bin", "console")

        if not os.path.exists(self._console):
            return dict(failed=True, changed=False, msg="missing bin/console")

        os.chdir(self.working_dir)

        dispatch: Dict[str, Any] = {
            "create": self.kimai_create_user,
            "activate": self.kimai_activate_user,
            "deactivate": self.kimai_deactivate_user,
            "promote": self.kimai_promote_user,
            "demote": self.kimai_demote_user,
        }

        handler = dispatch.get(self.state)
        if handler is None:
            return dict(
                failed=True,
                changed=False,
                msg=f"Unknown state: '{self.state}'",
            )

        return handler()

    # ------------------------------------------------------------------
    # Public state handlers
    # ------------------------------------------------------------------

    def kimai_create_user(self) -> Dict[str, Any]:
        """Create a new Kimai user account.

        Uses ``kimai:user:create <username> <email> <roles> <password>``.
        The method first queries the existing user list; if *username*
        already exists the command is skipped (idempotent).

        Returns:
            Ansible result dict.

        Note:
            ``email``, ``roles``, and ``password`` are all mandatory for
            user creation and are validated before the console call.
        """
        self.module.log("KimaiUser::kimai_create_user()")

        existing = self.kimai_list_users()
        self.module.log(msg=f"= existing users: '{existing.get('users')}'")

        if self.username in existing.get("users", []):
            return dict(failed=False, changed=False, msg="user is already created.")

        if not self.email:
            return dict(failed=True, changed=False, msg="missing email address.")

        validated_roles = self._validate_roles()
        if not validated_roles:
            return dict(failed=True, changed=False, msg="no valid roles specified.")

        if not self.password:
            return dict(failed=True, changed=False, msg="missing password.")

        args: List[str] = [
            self._console,
            "kimai:user:create",
            "--no-interaction",
            "--no-ansi",
            self.username,
            self.email,
            validated_roles,
            self.password,
        ]

        rc, out, _ = self.__exec(args, check_rc=False)

        if rc == 0:
            return dict(
                failed=False, changed=True, msg="user was successfully created."
            )

        return dict(failed=True, changed=False, msg=out)

    def kimai_activate_user(self) -> Dict[str, Any]:
        """Activate an existing Kimai user account.

        Uses ``kimai:user:activate <username>``.

        Returns:
            Ansible result dict.
        """
        self.module.log("KimaiUser::kimai_activate_user()")

        args: List[str] = [
            self._console,
            "kimai:user:activate",
            "--no-interaction",
            "--no-ansi",
            self.username,
        ]

        rc, out, _ = self.__exec(args, check_rc=False)

        if rc == 0:
            return dict(
                failed=False,
                changed=True,
                msg=f"User '{self.username}' activated.",
            )

        return dict(failed=True, changed=False, msg=out)

    def kimai_deactivate_user(self) -> Dict[str, Any]:
        """Deactivate an existing Kimai user account.

        Uses ``kimai:user:deactivate <username>``.

        Returns:
            Ansible result dict.
        """
        self.module.log("KimaiUser::kimai_deactivate_user()")

        args: List[str] = [
            self._console,
            "kimai:user:deactivate",
            "--no-interaction",
            "--no-ansi",
            self.username,
        ]

        rc, out, _ = self.__exec(args, check_rc=False)

        if rc == 0:
            return dict(
                failed=False,
                changed=True,
                msg=f"User '{self.username}' deactivated.",
            )

        return dict(failed=True, changed=False, msg=out)

    def kimai_promote_user(self) -> Dict[str, Any]:
        """Promote a Kimai user by granting one or more roles.

        Uses ``kimai:user:promote <username> <role>`` once per role.
        Invalid role identifiers are filtered out before the first
        console call; if the filtered list is empty the method returns
        a failure immediately.

        Returns:
            Ansible result dict.  ``changed`` is ``True`` when at least one
            role promotion succeeded.
        """
        self.module.log("KimaiUser::kimai_promote_user()")

        validated_roles = self._validate_roles()
        if not validated_roles:
            return dict(
                failed=True,
                changed=False,
                msg="No valid roles specified for promotion.",
            )

        return self._apply_role_command("kimai:user:promote", validated_roles)

    def kimai_demote_user(self) -> Dict[str, Any]:
        """Demote a Kimai user by revoking one or more roles.

        Uses ``kimai:user:demote <username> <role>`` once per role.
        Invalid role identifiers are filtered out before the first
        console call; if the filtered list is empty the method returns
        a failure immediately.

        Returns:
            Ansible result dict.  ``changed`` is ``True`` when at least one
            role revocation succeeded.
        """
        self.module.log("KimaiUser::kimai_demote_user()")

        validated_roles = self._validate_roles()

        if not validated_roles:
            return dict(
                failed=True,
                changed=False,
                msg="No valid roles specified for demotion.",
            )

        return self._apply_role_command("kimai:user:demote", validated_roles)

    def kimai_list_users(self) -> Dict[str, Any]:
        """Return a list of all registered Kimai usernames.

        Parses the tabular output of ``kimai:user:list``.  Only *active*
        users (rows ending with ``X``) are returned.

        Returns:
            A dict with keys ``failed`` (bool), ``changed`` (bool always
            ``False``), and ``users`` (list of username strings).
        """
        self.module.log("KimaiUser::kimai_list_users()")

        args: List[str] = [
            self._console,
            "kimai:user:list",
            "--no-interaction",
            "--no-ansi",
        ]

        rc, out, _ = self.__exec(args, check_rc=False)

        users: List[str] = []

        if rc == 0:
            for line in out.splitlines():
                match = _USER_LIST_RE.search(line)
                if match:
                    users.append(match.group("username"))

        return dict(failed=(rc != 0), changed=False, users=users)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _validate_roles(self) -> str:
        """Filter ``self.roles`` to known Kimai role identifiers.

        Returns:
            A comma-separated string of valid role names, e.g.
            ``"ROLE_ADMIN,ROLE_TEAMLEAD"``.  Returns an empty string when
            no valid roles remain after filtering.
        """
        self.module.log("KimaiUser::_validate_roles()")

        valid = [r for r in self.roles if r in _VALID_ROLES]
        return ",".join(valid)

    def _apply_role_command(
        self,
        console_command: str,
        roles_csv: str,
    ) -> Dict[str, Any]:
        """Execute a role-based console command once per role.

        Args:
            console_command: E.g. ``"kimai:user:promote"`` or
                ``"kimai:user:demote"``.
            roles_csv: Comma-separated string of validated role names.

        Returns:
            Aggregate Ansible result dict.  ``changed`` is ``True`` when at
            least one role operation succeeded.  ``failed`` is ``True`` when
            *all* role operations failed.
        """
        self.module.log(
            f"KimaiUser::_apply_role_command(console_command: {console_command}, roles_csv: {roles_csv})"
        )

        roles = [r.strip() for r in roles_csv.split(",") if r.strip()]
        messages: List[str] = []
        any_changed = False
        any_failed = False

        for role in roles:
            args: List[str] = [
                self._console,
                console_command,
                "--no-interaction",
                "--no-ansi",
                self.username,
                role,
            ]
            rc, out, _ = self.__exec(args, check_rc=False)

            if rc == 0:
                any_changed = True
                messages.append(f"{role}: OK")
            else:
                any_failed = True
                messages.append(f"{role}: FAILED – {out.strip()}")

        return dict(
            failed=(any_failed and not any_changed),
            changed=any_changed,
            msg="; ".join(messages),
        )

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
        state=dict(
            default="create",
            choices=["create", "activate", "deactivate", "promote", "demote"],
        ),
        username=dict(
            required=True,
            type="str",
        ),
        password=dict(
            required=False,
            type="str",
            no_log=True,
        ),
        email=dict(
            required=False,
            type="str",
        ),
        roles=dict(
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

    ku = KimaiUser(module)
    result = ku.run()

    module.log(msg=f"= result : '{result}'")
    module.exit_json(**result)


if __name__ == "__main__":
    main()

"""
bin/console kimai:user

Available commands for the "kimai:user" namespace:
  kimai:user:activate    Activate a user
  kimai:user:create      Create a new user
  kimai:user:deactivate  Deactivate a user
  kimai:user:demote      Demote a user by removing a role
  kimai:user:list        List all users
  kimai:user:password    Change the password of a user.
  kimai:user:promote     Promotes a user by adding a role
"""
