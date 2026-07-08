# coding: utf-8

from __future__ import annotations, unicode_literals

import os

import testinfra.utils.ansible_runner
from helper.molecule import get_vars, infra_hosts, local_facts

testinfra_hosts = infra_hosts(host_name="instance")

# --- tests -----------------------------------------------------------------

# _facts = local_facts(host=host, fact="kimai")


def test_directories(host, get_vars):

    base_dir = get_vars.get("kimai_install_base_directory")

    _facts = local_facts(host=host, fact="kimai")
    version = _facts.get("version")

    dirs = [
        base_dir,
        f"{base_dir}/kimai-{version}",
        f"{base_dir}/kimai/bin",
        f"{base_dir}/kimai/config",
        f"{base_dir}/kimai/vendor/",
        f"{base_dir}/kimai/var/cache",
        f"{base_dir}/kimai/var/cache/prod",
    ]

    # if 'latest' in install_dir:
    #     install_dir = install_dir.replace('latest', version)

    for _dir in dirs:
        f = host.file(_dir)
        assert f.is_directory


def test_files(host, get_vars):

    base_dir = get_vars.get("kimai_install_base_directory")

    files = [
        f"{base_dir}/kimai/bin/console",
        f"{base_dir}/kimai/config/routes.yaml",
        f"{base_dir}/kimai/config/services.yaml",
        f"{base_dir}/kimai/config/preload.php",
        f"{base_dir}/kimai/vendor/autoload.php",
        f"{base_dir}/kimai/var/cache/prod/App_KernelProdContainer.php",
    ]

    for _file in files:
        f = host.file(_file)
        assert f.is_file


def test_links(host, get_vars):

    base_dir = get_vars.get("kimai_install_base_directory")

    install_dir = f"{base_dir}/kimai"

    f = host.file(install_dir)
    assert f.is_symlink
