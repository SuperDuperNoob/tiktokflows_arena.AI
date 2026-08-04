# Rollback — back to tiktokflow_vps

If the unified tiktok-machine system has a problem you cannot fix in the
maintenance window, you can roll back to the previous tiktokflow_vps
(n8n/Docker) install. Target time: **under 30 minutes**.

This assumes you migrated with `deploy/migrate_from_vps.sh`, which created a
backup at `/opt/tiktokflow_backup/tiktokflow_vps_<TS>`.

---

## 0. Take a backup of the current tiktok-machine database first

Even on the way out you may want the analytics history later.

```bash
sudo systemctl stop tiktok-machine tiktok-webapp
sudo mkdir -p /opt/tiktok-machine-backup
sudo cp /opt/tiktok-machine/logs/tiktok.db /opt/tiktok-machine-backup/tiktok.db.$(date +%Y%m%d_%H%M%S)
sudo cp /opt/tiktok-machine/logs/burn_log.jsonl /opt/tiktok-machine-backup/ 2>/dev/null || true
sudo cp /opt/tiktok-machine/content/raw/preset_text.txt /opt/tiktok-machine-backup/ 2>/dev/null || true
```

## 1. Stop the tiktok-machine services

```bash
sudo systemctl disable --now tiktok-machine tiktok-webapp cloudflared
```

## 2. Restore the old tiktokflow_vps installation

```bash
TS=YYYYMMDD_HHMMSS                     # <- from the backup dir name
sudo mv /opt/tiktokflow_vps /opt/tiktokflow_vps_old_rollback 2>/dev/null || true
sudo cp -a /opt/tiktokflow_backup/tiktokflow_vps_$TS /opt/tiktokflow_vps
sudo chown -R archery:archery /opt/tiktokflow_vps
```

Restore the `.env` (credentials / proxy) if the backup holds one:

```bash
sudo cp /opt/tiktokflow_backup/.env_$TS /opt/tiktokflow_vps/.env 2>/dev/null || true
sudo chmod 600 /opt/tiktokflow_vps/.env
```

## 3. Restore cookies and the drive data the old system expects

```bash
# Cookies (they were copied from the same source, so nothing to do normally)
ls /opt/tiktokflow_vps/TiktokAutoUploader/CookiesDir

# Re-sync the drive root if product content was uploaded to the new layout
# while tiktok-machine was running. Point rclone at the same remote.
cd /opt/tiktokflow_vps
bash scripts/sync_in.sh || echo "sync_in optional - verify drive root is current"
```

## 4. Restart the old n8n/Docker stack

```bash
cd /opt/tiktokflow_vps
sudo docker compose up -d
```

## 5. Verify the old system works

```bash
docker ps                               # tiktokflow-n8n (and related) Up
docker exec -it tiktokflow-n8n bash -lc \
  'cd /home/archery/tiktokflow && python3 check_burns.py'
docker exec -it tiktokflow-n8n bash -lc \
  'cd /home/archery/tiktokflow && python3 generate_report.py'
```

Confirm:
- the n8n workflow `tiktokflow-v4.json` is active in the UI,
- `/status` answers on Telegram,
- at least one upload succeeds through the proxy.

## 6. Re-point Cloudflare Tunnel (if it was shared)

The old n8n UI is exposed by its own nginx on port 8080 (or via the existing
tunnel). Point the tunnel/ingress back to the n8n service and restart
`cloudflared`.

## 7. Timeline check

The whole sequence is: backup DB (1 min) → stop services (1 min) → restore
files (2 min) → docker compose up (2-5 min on a cold cache) → verify (5 min).
Under 30 minutes total, worst case.

## When to roll back vs. fix forward

| Situation | Do this |
|---|---|
| Proxy uploads failing / shadowbanned | Fix `config.yaml` proxy, don't roll back |
| A burn shipped a still image | `python3 check_burns.py --quarantine`, don't roll back |
| AI spending > 1 call/day | Confirm only `/growth` passes `--ai` |
| n8n downtime is unacceptable right now | Roll back |
| New DB schema is corrupt | Roll back and restore the DB backup |

After rollback, the tiktok-machine backup stays at `/opt/tiktok-machine-backup`
so you can re-migrate later without losing analytics.
