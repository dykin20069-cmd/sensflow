# Operations

## System Status

Open **System Status** in Telegram to verify:

- database connectivity;
- RBXCrate API connectivity and rounded balance;
- automation-loop state;
- active Marketplace Order count;
- pending PreOrder count.

Only the configured Telegram operator can access actions.

## Order states

- **Draft** — unpaid and editable; no RBXCrate order exists.
- **PreOrder** — paid and waiting for suitable stock.
- **Purchasing** — one external Marketplace Order is active.
- **Completed** — final quantities and financial snapshot are immutable.
- **Cancelled** — operator-cancelled and retained for history.

## PreOrders

PreOrders are checked automatically when automatic reorder is enabled. Confirm the configured rate ceiling, reorder interval, RBXCrate balance, and detailed stock before treating a waiting PreOrder as an incident.

## Manual operational actions

The System Status screen provides:

- **Run Sync Pass Now** — immediately checks active Marketplace Orders and reports the number processed.
- **Run Recovery Now** — checks Purchasing orders, synchronizes recoverable attempts, returns true orphans to PreOrder, and reports checked/repaired counts.

These operations are idempotent and use the same services as normal startup and automation.

## Crash recovery

On every process start, recovery runs before automation and Telegram polling. Purchasing orders with active or completed attempts are synchronized. Purchasing orders without a recoverable attempt return to PreOrder. Unfinished completed attempts are retried during later synchronization passes if an external dependency was temporarily unavailable.

## Dry-run verification

Set `RBXCRATE_DRY_RUN=true` and restart the application. Dry-run mode performs no network request to RBXCrate and spends no balance. It supplies deterministic stock and advances new attempts from Pending to Processing and then Completed over synchronization passes.

Never treat the displayed dry-run balance as real account funds.

## Rotate the RBXCrate API key

1. Create the replacement credential in RBXCrate.
2. Update `RBXCRATE_API_KEY` in `.env` without logging or sharing it.
3. Restart the application container.
4. Verify RBXCrate API status and balance in Telegram.
5. Revoke the previous credential after verification.

## Backup and restore

Run `./scripts/backup.sh` before releases and on a regular schedule. Follow [BACKUP.md](BACKUP.md) for destructive restore confirmation and isolated restoration testing.
