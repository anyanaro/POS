# Nginx, Waitress, and NSSM deployment

Use the server's existing Nginx service as the public TLS reverse proxy and run the Django application using two independent Waitress services. This is the recommended architecture for this Windows host because Nginx already owns ports 80 and 443; Waitress runs Django; NSSM restarts all application processes at boot and after failures.

## Environments

- Test: `https://testfarma24pos.ibsgroupbc365.com` -> `http://127.0.0.1:8101` -> current `django_db` data.
- Live: `https://farma24pos.ibsgroupbc365.com` -> `http://127.0.0.1:8102` -> empty `POS Live` database.

Copy `.env.test.example` to `.env.test` and `.env.live.example` to `.env.live`. Set unique secrets and PostgreSQL passwords. Never commit these two real environment files.

## One-time setup

1. Install Waitress into the Python environment used by the services: `python -m pip install waitress`.
2. Run PowerShell as Administrator: `./scripts/install_pos_services.ps1`.
3. Run `./scripts/deploy_live_database.ps1` once. It creates `POS Live`, migrates its schema, and collects its static files. It does not copy operational data.
4. Issue the certificate with win-acme, then run `./scripts/configure_nginx_pos.ps1`. It adds the two HTTPS host routes, proxies to the private Waitress ports, serves each environment's static/media directory, validates Nginx, and reloads it.
5. Restrict access to ports 8101 and 8102 to localhost only.

Before exposing either site, run `python manage.py check --deploy` through its respective environment and verify both HTTPS host bindings return the expected login page.

## Release promotion

Develop in `D:\ssl\django-projects\POS`. Run `D:\ssl\django-projects\POS\scripts\promote_release.ps1 -Environment test` to copy that workspace to `POS-test`, validate it, migrate the test database, collect test static files, and restart only `POS-Test`.

After test approval, run `D:\ssl\django-projects\POS\scripts\promote_release.ps1 -Environment live`. This copies `POS-test` (not the editable workspace) to `POS-live`, validates it, migrates the live database, collects live static files, and restarts only `POS-Live`.