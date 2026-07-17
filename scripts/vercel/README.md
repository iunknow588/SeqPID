# Vercel Scripts

This folder contains the deployment helpers for `webUI/tongstock-master/web`.

## Files

- `deploy_webui.*` - the only public entrypoint for link, preflight, sync, deploy, and smoke.
- `_common.ps1` - shared helper functions.

## Default target

The default deployment target is:

`webUI/tongstock-master/web`

## Environment file

Use `scripts/vercel/.env` for local values and `scripts/vercel/.env.example` as the template.
Default page domain: `gp.cdao.online`

## Suggested flow

```powershell
deploy_webui.cmd -AutoLink -Build -SyncEnv -Execute -Prod -Smoke -SmokeApi
```

`-Smoke` verifies the deployed SPA homepage and a deep route.

`-SmokeApi` only makes sense when `VITE_API_BASE` points to a real backend API.
