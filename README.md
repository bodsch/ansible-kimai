
# Ansible Role:  `kimai`

Install an kimai from [sources](https://github.com/kimai/kimai).

> Kimai is a web-based multi-user time-tracking application. 
> Works great for everyone: freelancers, companies, organizations - everyone can track their times, 
> generate reports, create invoices and do so much more.


[![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/bodsch/ansible-kimai/main.yml?branch=main)][ci]
[![GitHub issues](https://img.shields.io/github/issues/bodsch/ansible-kimai)][issues]
[![GitHub release (latest by date)](https://img.shields.io/github/v/release/bodsch/ansible-kimai)][releases]
[![Ansible Quality Score](https://img.shields.io/ansible/quality/50067?label=role%20quality)][quality]

[ci]: https://github.com/bodsch/ansible-kimai/actions
[issues]: https://github.com/bodsch/ansible-kimai/issues?q=is%3Aopen+is%3Aissue
[releases]: https://github.com/bodsch/ansible-kimai/releases
[quality]: https://galaxy.ansible.com/bodsch/kimai


## Requirements & Dependencies

- running mariadb / mysql database
- PHP > 8.0
- nginx

### Ansible Collections

- [bodsch.core](https://github.com/bodsch/ansible-collection-core)

```bash
ansible-galaxy collection install bodsch.core
```
or
```bash
ansible-galaxy collection install --requirements-file collections.yml
```


## tested operating systems

* Debian based
    - Debian 10 / 11 / 12
    - Ubuntu 20.04

## Contribution

Please read [Contribution](CONTRIBUTING.md)

## Development,  Branches (Git Tags)

The `master` Branch is my *Working Horse* includes the "latest, hot shit" and can be complete broken!

If you want to use something stable, please use a [Tagged Version](https://github.com/bodsch/ansible-kimai/tags)!

---


## Configuration

```yaml
kimai_version: 2.0.29

kimai_direct_download: false

kimai_release: {}

kimai_install_base_directory: /var/www

kimai_owner: www-data
kimai_group: www-data

kimai_database:
  # username: kimai
  # password:
  # hostname:
  # port: 3306
  # schema: kimai
  server:
    version: ""

kimai_env: prod

kimai_mailer:
  from: kimai@test.tld
  url: null://null

kimai_admin_user:
  username: admin
  password: admin0815
  email: admin@test.tld

kimai_secret: change_this_to_something_unique
```

----

## Author and License

- Bodo Schulz

## License

[Apache](LICENSE)

**FREE SOFTWARE, HELL YEAH!**
