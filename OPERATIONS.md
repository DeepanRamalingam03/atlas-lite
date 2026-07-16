# Atlas Lite Production Operations

## Services

```bash
systemctl is-active atlas-lite-runtime
systemctl is-active atlas-lite-discord
systemctl is-active atlas-lite-alerts
```

## Add autonomous work through Discord

```text
!addtask 10 | Task title | Exact implementation goal with tests
```

## Runtime commands

```text
!status
!runtime
!heartbeat
!roadmap
!workflow
!alerts
!ackalerts
!pause <task_id>
!resume <task_id>
```

## Logs

```bash
sudo journalctl -u atlas-lite-runtime -f
sudo journalctl -u atlas-lite-discord -f
sudo journalctl -u atlas-lite-alerts -f
```

## Restart

```bash
sudo systemctl restart atlas-lite-runtime
sudo systemctl restart atlas-lite-discord
sudo systemctl restart atlas-lite-alerts
```

## Safety boundaries

Atlas pauses or blocks work for low disk space, tracked Git changes,
repository lock conflicts, wrong branches, protected paths, credentials,
OTP, MFA, CAPTCHA, architecture decisions, destructive actions, production
deployment approvals, financial-risk actions, and exhausted retries.

## Default production values

```text
ATLAS_MINIMUM_FREE_DISK_MB=256
ATLAS_MINIMUM_FREE_DISK_PERCENT=5
ATLAS_RUNTIME_MAX_ATTEMPTS=4
ATLAS_RUNTIME_RETRY_INITIAL_SECONDS=30
ATLAS_RUNTIME_RETRY_MULTIPLIER=2
ATLAS_RUNTIME_RETRY_MAX_SECONDS=900
ATLAS_HEARTBEAT_STALE_SECONDS=120
ATLAS_ALERT_POLL_SECONDS=30
```
