# music-server setup and Navidrome retirement

[music-server](https://github.com/MatthewDavidMiller/music-server) is the
first-party Subsonic server that replaces Navidrome on VM1. It serves the
Nextcloud `Music` folder, read-only, to Subsonic apps such as play:Sub. It
supports several accounts, each with their own playlists, stars, and play
counts, and transcodes to MP3 or Opus when a phone asks for a lower bitrate.
It needs no database.

The migration runs in two phases. Phase A (sections 1 to 4) runs music-server
at `music.<domain>` beside Navidrome until it has been checked with real
listening. Phase B (section 5) removes Navidrome. Nothing is migrated from
`navidrome.db`: playlists are recreated by hand, and stars and play counts
start fresh.

---

## 1. Release and lock the image

In the music-server repository:

```bash
gh auth token | podman login ghcr.io -u MatthewDavidMiller --password-stdin
make release
```

`make release`:
1. runs the gate and the image tests under VM1's flags;
2. pushes `ghcr.io/matthewdavidmiller/music-server:<version>`;
3. tags the release;
4. creates a GitHub release whose notes carry the digest.

Then, on GitHub, make the package public (Package settings → Change
visibility). VM1 pulls images anonymously, and the image holds no secrets.

`vm1.yml` turns the role on once the lock has a reviewed digest for
`music_server`, so **finish section 2 before this step's last part.**

For the first release only (done for 0.1.0), add the entry the review tool works from to
`artifacts/containers.lock.yml`, under `artifact_locked_images`:

```yaml
  music_server:
    upstream_ref: ghcr.io/matthewdavidmiller/music-server:0.1.0
    approved_tag: 0.1.0
    internal_repo: homelab/music-server
    signature_required: false
    first_party: true
```

Then let the tool review it and write the tag and digest:

```bash
bash scripts/review_container_updates.sh --service music_server
```

`first_party: true` skips the 24-hour age gate; see
[container-image-updates.md](container-image-updates.md#first-party-images).
Later releases need only the review command.

## 2. Inventory

Generate the master key:

```bash
podman run --rm --entrypoint music-server ghcr.io/matthewdavidmiller/music-server:0.1.0 gen-key
```

Store it in Vaultwarden as well as the vault. Then add to the externally
managed inventory:

```yaml
music_server_path: /srv/music-server        # holds data/ and cache/
music_server_music_path: "{{ nextcloud_path }}/data/{{ nextcloud_homelab_user }}/files/Music"
music_server_master_key: !vault |
  ...
music_server_users: !vault |                # a list of {name, password, admin}
  ...
music_server_backup_location: Nextcloud:music_server_backup
```

`music_server_users` decrypts to a list like this:

```yaml
- name: matt
  password: a-long-unique-password
  admin: true
- name: guest
  password: another-long-password
```

The account rules:
- At least one account must be an admin; only admins can open the status
  page.
- Passwords are 8-128 characters.
- Use passwords that are not used anywhere else. The Subsonic protocol needs
  the server to know them.

The network addresses, DNS alias, and Traefik route come from the
repository's plan, [`network/vm1.yml`](../../network/vm1.yml), and `vm1.yml`
adds `music_server` to `container_service_names` itself, so the inventory
needs none of them. The route is `music.<homelab_internal_domain>`, with
`proxy_management_only: true` and `proxy_access_log: false` (Subsonic
credentials are in the query string).

Like every VM1 route, it is management-only: Traefik answers only clients
inside `management_network` (or `ip_ansible`), so phones reach it through
the VPN.
That works when the VPN server NATs its clients onto the LAN, so requests
arrive from a LAN address. A VPN that routes its own subnet without NAT
needs that subnet in `management_network`, which also opens the firewall's
management rules (SSH) to VPN clients.

Add the DNS record for `music.<homelab_internal_domain>`. It must resolve to an address the
phone reaches through the VPN, normally VM1's LAN address (a private A record,
or an override in the VPN's resolver). The certificate still issues, because
the DNS-01 challenge never connects to the server.

## 3. Deploy

Run `vm1.yml` (or `update_homelab_vms.yml`). VM1 stages runtime changes,
so the server starts after the reboot. Then:

```bash
podman logs music_server     # "accounts added: ...", then "scan finished: N tracks"
```

Open `https://music.<domain>/` and sign in as an admin. The status page
shows the library's size and any files the scan could not read, with the
reason. The first scan reads every file; later scans only read new or
changed ones.

To check the library before deploying, run `scan-report` against it once.
It reads the library without writing anything and prints counts, problems,
and peak memory:

```bash
podman run --rm --read-only -v "<music path>:/music:ro,z" \
  --entrypoint music-server ghcr.io/matthewdavidmiller/music-server:0.1.0 scan-report
```

## 4. Check it with play:Sub

Add `music.<domain>` as a second server in play:Sub and use it for a few
days. Check:

1. **Library:** browse artists and albums, open folders, search.
2. **Cover art:** it appears in lists and on the player.
3. **Playback:** play on Wi-Fi (the original file) and on cellular with a
   bitrate limit set in play:Sub (a transcode; the status page counts
   transcodes).
4. **Offline:** download an album and play it in airplane mode.
5. **Playlists and stars:** recreate a playlist, edit it, and star a few
   songs.
6. **Other accounts:** a second user sees their own playlists.

If play:Sub uses a call the server does not implement, the status page
lists it under Activity, and the log has `unknown subsonic method <name>`.
Report those as music-server issues before retiring Navidrome.

`podman stats music_server` shows the memory in use. The default 512 MiB
(`music_server_memory`) has plenty of headroom.

## 5. Retire Navidrome (Phase B)

Once music-server has replaced Navidrome in daily use, a follow-up change to
this repository:
- removes the `navidrome` role, its lock entry, and its `vm1.yml` wiring;
- removes its route dictionary entries;
- adds a `retire_navidrome.yml` playbook that removes the container, unit,
  scripts, cron job, route file, image, and network from VM1.

The Navidrome data directory and its old backups are kept until deleted by
hand. Remove the Navidrome inventory variables and DNS record, and the old server in play:Sub.
