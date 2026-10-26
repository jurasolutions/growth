# 18 — A local D1 stand-in for UAT

Status: ready-for-agent
Blocked by: 17

## Problem

In UAT, `live_problems` lists "D1 is not configured", and with real or fake credentials the first approved send would call Cloudflare. UAT must never reach a real service.

## What to change

Add a guarded `JURA_GROWTH_D1_BASE_URL` that the D1 client honours only when it points at a loopback address, served by `tests/resend_stub.py` (or a sibling stub). Refuse any non-loopback override. Wire it into the UAT seed and `uat.md`'s environment block.

## Acceptance criteria

- With the override set to a loopback stub, sync and the D1 checks in `live_problems` use the stub; no request leaves the machine (network guard test).
- A non-loopback override is refused with a clear error.
- `uv run pytest -rs` passes with 0 skipped.

## Pointers

- Ticket 17 report (crew-log); `jura_growth/cloudflare.py`; `tests/resend_stub.py`; `.scratch/mission-control/uat.md`
