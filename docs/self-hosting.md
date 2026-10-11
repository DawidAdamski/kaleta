# Self-hosting Kaleta

One machine, one compose file: Kaleta and PostgreSQL in containers, HTTPS so
the app installs on a phone, and backups that you make and keep. This page
goes from an empty server to a restore you have tried at least once.

The building blocks are [`docker-compose.yml`](https://github.com/DawidAdamski/kaleta/blob/main/docker-compose.yml)
and the optional overlays in [`deploy/selfhost/`](https://github.com/DawidAdamski/kaleta/tree/main/deploy/selfhost).
Every command below works with `docker compose` in place of `podman compose`.

## Requirements

| | |
|---|---|
| Machine | Any 64-bit Linux box, mini PC or NAS that runs containers (amd64 or arm64). One or two CPU cores are plenty. |
| Memory | **1 GB** is comfortable. Measured on the compose stack with six years of example data: Kaleta idles at about 150 MB and peaked at about 320 MB while drawing the forecast and the reports; PostgreSQL uses about 60 MB. |
| Disk | About 2 GB for the images. The data is small. An empty instance is about 11 MB of database. Six years of example ledger (1,600 transactions with budgets and payees) made the family's own schema 3.2 MB, which is roughly **2 kB per transaction**, history included. A household entering 2,000 transactions a year grows by about 4 MB a year. A compressed dump of those six years is 1.2 MB. |
| Software | Podman 4+ or Docker, with **Docker Compose 2.24 or newer** (`podman compose version` / `docker compose version`). `podman compose` runs Docker Compose when it is installed. The overlays need 2.24 for `ports: !override`. An older Compose would leave port 8080 open on every interface. |

## Install

```bash
git clone https://github.com/DawidAdamski/kaleta.git
cd kaleta
mkdir backups          # yours, so the dumps in it are yours too
```

### Choose your compose files once

The base file runs Kaleta. The overlays add backups and HTTPS. List the ones
you use in `COMPOSE_FILE` in a `.env` file next to `docker-compose.yml`.
Compose reads it on every command, so every `podman compose …` below uses
the same set. Without it, a command typed with fewer `-f` files would rebuild
`kaleta` from the base file alone and undo the overlays: port 8080 open to
the network again, the proxy left behind.

```bash
# .env — backups now; add an HTTPS overlay when you get to that section
COMPOSE_FILE=docker-compose.yml:deploy/selfhost/backup.yml
```

### Start it

```bash
podman compose up -d --build --wait
```

The first `up` builds the image (a few minutes) and starts:

- `secrets`, once: it writes a random database password and
  `KALETA_SECRET_KEY` into the `kaleta-secrets` volume. Later starts reuse
  them, so no secret ever goes into a file you edit.
- `db`: PostgreSQL 18, with its data in the `kaleta-pg` volume.
- `kaleta`: the app on port 8080. It brings the database to the current
  schema on every start.
- `backup`: the nightly dump (see [Backups](#backups)).

### The administrator comes first

The first sign-up on an empty instance becomes its **administrator**. The
base file publishes port 8080 on every interface, so on a machine others can
reach, create the administrator from the shell right after the first `up`:

```bash
podman compose exec kaleta uv run kaleta-admin create-login you@example.com --admin
```

It prints a one-time password. Sign in with it at `http://<server>:8080` and
choose your own. If nobody else can reach the machine, you can instead open
`http://localhost:8080` and sign up there.

Next comes the **data passphrase**:

- The passphrase encrypts everything your family writes: descriptions,
  payees, category and account names, notes. The server holds the key only
  while a member of the family is signed in and has unlocked it. While nobody
  is, whoever runs the machine cannot read the data, and that includes you as
  its administrator.
- The **recovery code** shown right after is the only other way in. Save it
  somewhere other than this server, for example in a password manager.
- **Lose both, and the data is gone.** Nobody can reset a passphrase,
  because nothing on the server can open the key without it. The login
  password is a different thing, and the administrator can reset that.

After a restart of the `kaleta` container every member types the passphrase
again (the page asks for it). That is expected.

### Families and sign-up

The administrator's page, **Administration** in the navigation (`/admin`),
manages the instance. It shows e-mail addresses, counts and statuses, never a
family's data.

- **New family** creates a family with its owner's login. The page shows a
  one-time password, which the owner replaces at their first sign-in, and
  then the owner chooses the family's data passphrase.
- **Who may sign up**: *closed* (the default: only the administrator creates
  families), *by invitation*, or *open* (anyone who reaches the address
  creates a family of their own; keep it closed on a home server).
- **Logins**: reset a forgotten password (signs that person out everywhere),
  disable a login, make someone else an administrator too.
- A family is one login today. Inviting the rest of the household into the
  same family comes with household sharing.

The same operations exist on the command line, for when the page is out of
reach: `podman compose exec kaleta uv run kaleta-admin --help`.

## HTTPS (needed to install the app)

A browser installs Kaleta as an app (a PWA) only from an `https://` address
(or from `localhost`). Pick one of the two options below. Each overlay binds
the plain port 8080 to loopback, so only the proxy reaches the app, and marks
the session cookie `Secure`. Add the overlay to `COMPOSE_FILE` and its
setting to `.env`, then `podman compose up -d`.

### Option A: Cloudflare Tunnel (no open ports)

`cloudflared` makes an outgoing connection to Cloudflare, so nothing on your
router needs forwarding. You need a domain on Cloudflare.

1. In the Cloudflare dashboard go to **Zero Trust → Networks → Tunnels →
   Create a tunnel** (type *Cloudflared*) and copy its token.
2. Add a **public hostname**, e.g. `kaleta.example.com`, with the service
   `http://kaleta:8080`.
3. On the server, `.env` becomes:

    ```bash
    COMPOSE_FILE=docker-compose.yml:deploy/selfhost/backup.yml:deploy/selfhost/cloudflared.yml
    CLOUDFLARE_TUNNEL_TOKEN=eyJ...
    ```

    and `podman compose up -d`.

Open `https://kaleta.example.com` on the phone and choose *Install app* (or
*Add to Home Screen*). The overlay pins a `cloudflared` release; Cloudflare
stops supporting old ones, so update the pin when you upgrade Kaleta.

### Option B: Caddy with an automatic certificate

Caddy obtains and renews a Let's Encrypt certificate itself. You need a DNS
name pointing at the server, with ports 80 and 443 forwarded to it.

```bash
# .env
COMPOSE_FILE=docker-compose.yml:deploy/selfhost/backup.yml:deploy/selfhost/caddy.yml
KALETA_DOMAIN=kaleta.example.com
```

The certificate is kept in the `kaleta-caddy` volume. Rootless Podman cannot
bind ports below 1024 by default; either run
`sudo sysctl net.ipv4.ip_unprivileged_port_start=80` (and persist it in
`/etc/sysctl.d/`), or use option A.

## Backups

Kaleta makes no backups of its own (ADR-38): whoever runs the database owns
them. The `backup` service (`deploy/selfhost/backup.yml`, in `COMPOSE_FILE`
since the install) runs `pg_dump` every night at 03:00 and keeps two weeks
of dumps.

- Dumps go to `./backups/kaleta-YYYY-MM-DD.dump` (pg_dump's compressed
  custom format), mode `0600`, owned by whoever owns the directory. Create
  it yourself, as the install did. If Docker creates it, it belongs to root,
  and so do the dumps (use `sudo` to read them).
- `KALETA_BACKUP_DIR` in `.env` chooses another directory,
  `KALETA_BACKUP_KEEP_DAYS` the retention (default 14), and `TZ` the clock
  the 03:00 is read on (default UTC).
- A dump right now: `podman compose exec backup kaleta-backup`. Give it a
  name to keep it apart from the nightly one:
  `podman compose exec backup kaleta-backup before-upgrade`.
- Each run writes one line to `podman compose logs backup`. Look there now
  and then; a failed night says so there and nowhere else.

A backup on the same disk does not survive the disk. **Copy the dumps off the
machine**, for example with a nightly `rsync` or `rclone` from the host:

```bash
# crontab -e on the host — after the 03:00 dump
30 3 * * * rclone copy /srv/kaleta/backups remote:kaleta-backups --max-age 48h
```

### What a dump contains

- The ciphertext of everything your family wrote (descriptions, payees,
  names, notes). It opens only with a member's data passphrase or recovery
  code, as the live database does.
- **In the clear**: amounts, dates, currencies, budget figures and the
  members' e-mail addresses ([privacy.md](privacy.md) says what is encrypted
  and what is not). Store the dumps accordingly. If you want them encrypted
  at rest as well, pipe them through [`age`](https://age-encryption.org)
  before they leave the machine:
  `age -r <your public key> kaleta-….dump > kaleta-….dump.age`.

Two-factor sign-in secrets are encrypted under `KALETA_SECRET_KEY`, which
lives in the `kaleta-secrets` volume and not in the dump. Keep a copy in the
same password manager as your recovery code; this prints it:
`podman compose exec kaleta cat /run/secrets/kaleta_secret_key`. Without it,
a restore on a new machine works, but two-factor sign-in must be turned off
for each member who had it: `kaleta-admin reset-password <e-mail> --disable-mfa`.

### Restore

This replaces the database with a dump.

```bash
DUMP=backups/kaleta-2026-10-11.dump

# 1. Stop the app and the nightly dump.
podman compose stop kaleta backup

# 2. Throw the database away and start an empty one. Volumes are named after
#    the compose project (`name: kaleta`): kaleta_kaleta-pg.
podman compose rm -sf db
podman volume rm kaleta_kaleta-pg
podman compose up -d --wait db

# 3. Load the dump into it.
podman compose exec -T db pg_restore -U kaleta -d kaleta --no-owner < "$DUMP"

# 4. Start everything, sign in, unlock with the data passphrase.
podman compose up -d --wait
```

`--wait` matters in step 2. If `pg_restore` runs before PostgreSQL accepts
connections, nothing is restored, and Kaleta then starts on an empty database.

**On a new machine**, clone the repository, write `.env` and
`mkdir backups` as in the install. If you kept the secret key, put it into
the secrets volume *before* the first `up`: the `secrets` service never
replaces a file that is there. Then run steps 2 to 4.

```bash
# The key from your password manager, into a file for a moment:
(umask 077; printf '%s' '<your kaleta_secret_key>' > kaleta_secret_key)
podman volume create kaleta_kaleta-secrets
podman run --rm -v kaleta_kaleta-secrets:/s -v "$PWD":/h:ro docker.io/library/alpine:3.22 \
  sh -c 'install -m 0600 /h/kaleta_secret_key /s/kaleta_secret_key'
rm kaleta_secret_key
```

These steps were tried on Podman: the kept key stayed, and the `secrets`
service wrote only the files that were missing.

### The restore drill: do it once

A backup you have never restored is a hope. Try it once now, while
nothing depends on it:

1. Take a dump (`podman compose exec backup kaleta-backup`) and copy it off
   the machine.
2. Run the restore above with that copy.
3. Sign in, unlock with the passphrase, open **Transactions**: the
   descriptions read normally and the last thing you entered is there.

This guide's drill was run on the compose stack with six years of example
data. The dump was taken, the volume dropped and the dump restored, and the
family unlocked with its passphrase showing every transaction.

## Upgrades

```bash
podman compose exec backup kaleta-backup before-upgrade
git pull
podman compose up -d --build --wait
```

Kaleta migrates the database when it starts. If the instance's registry
fails to migrate, Kaleta refuses to start and says why
(`podman compose logs kaleta`). A family whose own schema fails is suspended
instead, and the others carry on. The administrator resumes it once fixed
(`kaleta-admin resume <id>`).

To roll back, the order matters, because migrations only go forward and an
older Kaleta cannot run on a database a newer one has migrated:

1. `git checkout <the previous tag>` and `podman compose build kaleta`.
2. Restore `backups/kaleta-before-upgrade.dump` as above (steps 1 to 4).

A later `kaleta-backup before-upgrade` overwrites that file, and the nightly
retention deletes it after two weeks. Copy it aside if you want to keep it.
