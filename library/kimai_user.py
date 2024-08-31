#!/usr/bin/python3
# -*- coding: utf-8 -*-

# (c) 2022-2024, Bodo Schulz <bodo@boone-schulz.de>
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


class KimaiUser(object):
    """
    """
    module = None

    def __init__(self, module):
        """
        """
        self.module = module

        self.state = module.params.get("state")
        self.working_dir = module.params.get("working_dir")
        self.environment = module.params.get("environment")
        self.username = module.params.get("username")
        self.password = module.params.get("password", None)
        self.email = module.params.get("email", None)
        self.roles = module.params.get("roles", None)

    def run(self):
        """
        """
        self._console = os.path.join(self.working_dir, 'bin', 'console')

        self.module.log(msg=f" console   : '{self._console}'")

        if not os.path.exists(self._console):
            return dict(
                failed = True,
                changed = False,
                msg = "missing bin/console"
            )

        os.chdir(self.working_dir)

        if self.state == "create":
            return self.kimai_create_user()

        if self.state == "activate":
            return self.kimai_activate_user()

        if self.state == "deactivate":
            return self.kimai_deactivate_user()

        if self.state == "promote":
            return self.kimai_promote_user()

        if self.state == "demote":
            return self.kimai_demote_user()

    def kimai_create_user(self):
        """
          bin/console kimai:user:create --help
          Description:
            Create a new user

          Usage:
            kimai:user:create [options] [--] <username> <email> [<role> [<password>]]

          Arguments:
            username                A name for the new user (must be unique)
            email                   Email address of the new user (must be unique)
            role                    A comma separated list of user roles, e.g. "ROLE_USER,ROLE_ADMIN" [default: "ROLE_USER"]
            password                Password for the new user (requested if not provided)
        """
        _failed = True
        _changed = False

        created_users = self.kimai_list_users()

        created_users = created_users.get('users')

        self.module.log(msg=f"= created_users : '{created_users}'")

        if self.username in created_users:
            # TODO
            # check roles
            return dict(
                failed = False,
                changed = False,
                msg = "user is already installed."
            )

        args = []
        args.append(self._console)
        args.append("kimai:user:create")
        args.append("--no-interaction")
        args.append("--no-ansi")

        if self.username:
            args.append(self.username)

        if self.email:
            args.append(self.email)
        else:
            return dict(
                failed=True,
                msg="missing email address."
            )

        if self.roles and len(self.roles) > 0:
            _roles = self.__validate_roles()
            args.append(_roles)
        else:
            return dict(
                failed=True,
                msg="missing roles"
            )

        if self.password:
            args.append(self.password)
        else:
            return dict(
                failed=True,
                msg="missing password."
            )

        rc, out, err = self.__exec(args, check_rc=False)

        if rc == 0:
            _failed = False
            _changed = True
            _msg = "user was successfully created."

        else:
            _msg = out
            _failed = False

        return dict(
            failed=_failed,
            changed=_changed,
            msg=_msg
        )

    def kimai_list_users(self):
        """
          bin/console kimai:user:list --help
          Description:
            List all users

          Usage:
            kimai:user:list
        """
        _failed = True
        _changed = False
        users = []

        args = []
        args.append(self._console)
        args.append("kimai:user:list")
        args.append("--no-interaction")
        args.append("--no-ansi")

        rc, out, err = self.__exec(args, check_rc=False)

        if rc == 0:
            pattern = re.compile(r"\s+(?P<username>[a-zA-Z]+)\s+(?P<email>[a-zA-Z\@\.]+)\s+(?P<roles>[A-Z_,\ ]+)(?P<active>X)", re.MULTILINE)

            for line in out.splitlines():
                # self.module.log(msg=f"line     : {line}")
                for match in re.finditer(pattern, line):
                    result = re.search(pattern, line)
                    users.append(result.group('username'))

        return dict(
            failed=_failed,
            changed=_changed,
            users=users
        )

    def kimai_activate_user(self):
        """
          bin/console kimai:user:activate --help
          Description:
            Activate a user

          Usage:
            kimai:user:activate <username>

          Arguments:
            username              The username
        """

    def kimai_deactivate_user(self):
        """
          bin/console kimai:user:deactivate --help
          Description:
            Deactivate a user

          Usage:
            kimai:user:deactivate <username>

          Arguments:
            username              The username
        """

    def kimai_promote_user(self):
        """
          bin/console kimai:user:promote --help
          Description:
            Promotes a user by adding a role

          Usage:
            kimai:user:promote [options] [--] <username> [<role>]

          Arguments:
            username              The username
            role                  The role

          php bin/console kimai:user:promote susan_super ROLE_TEAMLEAD
          php bin/console kimai:user:promote --super susan_super

          public const ROLE_USER = 'ROLE_USER';
          public const ROLE_TEAMLEAD = 'ROLE_TEAMLEAD';
          public const ROLE_ADMIN = 'ROLE_ADMIN';
          public const ROLE_SUPER_ADMIN = 'ROLE_SUPER_ADMIN';

        """

    def kimai_demote_user(self):
        """
          bin/console kimai:user:demote --help
          Description:
            Demote a user by removing a role

          Usage:
            kimai:user:demote [options] [--] <username> [<role>]

          Arguments:
            username              The username
            role                  The role

          php bin/console kimai:user:demote susan_super ROLE_TEAMLEAD
          php bin/console kimai:user:demote --super susan_super
        """

    def __validate_roles(self):
        """
          ROLE_USER
          ROLE_TEAMLEAD
          ROLE_ADMIN
          ROLE_SUPER_ADMIN
        """
        valide_roles = [
            "ROLE_USER",
            "ROLE_TEAMLEAD",
            "ROLE_ADMIN",
            "ROLE_SUPER_ADMIN",
        ]

        _roles = [x for x in self.roles if x in valide_roles]

        # if self.roles and len(self.roles) > 0:
        #     for r in self.roles:
        #         if r in valide_roles:
        #             _roles.append(r)

        return ",".join(_roles)

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
        state=dict(
            default="create",
            choices=[
                "create",
                "activate",
                "deactivate",
                "promote",
                "demote"
            ]
        ),
        username=dict(
            required=True,
            type=str,
        ),
        password=dict(
            required=False,
            type=str,
            no_log=True,
        ),
        email=dict(
            required=False,
            type=str,
        ),
        roles=dict(
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
            default="prod"
        )
    )

    module = AnsibleModule(
        argument_spec=specs,
        supports_check_mode=False,
    )

    kc = KimaiUser(module)
    result = kc.run()

    module.log(msg=f"= result : '{result}'")

    module.exit_json(**result)


# import module snippets
if __name__ == '__main__':
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
