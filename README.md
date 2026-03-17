# Unified Storage Management System

This repository contains a reusable storage control plane for tracking and managing your local disk, Google Drive accounts, and OneDrive from one place.

It gives you:

- A unified dashboard and API for local and cloud storage.
- Real-time or on-demand scans of available space across providers.
- Anthropic-powered storage insights and balancing recommendations.
- A backend you can reuse from other projects through REST endpoints.
- A deployment path that works locally or on a remote server.

## What This System Does

This project unifies storage visibility and management. It does **not** turn Google Drive, OneDrive, and your SSD into a single physical filesystem by itself.

If you want a true single mounted drive later, use this backend together with an overlay tool such as `rclone union` or another sync or mount layer. This project is the control plane and monitoring layer.

## Stack

- FastAPI for the API and dashboard host
- Provider adapters for local storage, Google Drive, and OneDrive
- Anthropic API for smart recommendations
- YAML account registry so you can add many accounts cleanly
- Docker support for access from anywhere

## Project Layout

- [app/main.py](/workspaces/storage_management_system/app/main.py)
- [app/services/storage_manager.py](/workspaces/storage_management_system/app/services/storage_manager.py)
- [app/services/anthropic_service.py](/workspaces/storage_management_system/app/services/anthropic_service.py)
- [config/accounts.example.yaml](/workspaces/storage_management_system/config/accounts.example.yaml)

## Quick Start

1. Create a virtual environment and install dependencies.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Create your environment file.

```bash
cp .env.example .env
```

3. Create your account configuration file.

```bash
cp config/accounts.example.yaml config/accounts.yaml
```

4. Put secrets only in `.env` and keep `config/accounts.yaml` as a non-secret registry that references those environment variables.

Example:

```env
GOOGLE_SHARED_CLIENT_ID=your_google_client_id
GOOGLE_SHARED_CLIENT_SECRET=your_google_client_secret
GOOGLE_01_REFRESH_TOKEN=refresh_token_for_labonysur473
MICROSOFT_CLIENT_ID=your_microsoft_client_id
MICROSOFT_REFRESH_TOKEN=your_microsoft_refresh_token
ANTHROPIC_API_KEY=your_anthropic_api_key
```

The tracked YAML template already uses `${ENV_VAR}` placeholders, so your real keys and tokens stay outside git.

5. Run the API.

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

6. Open `http://localhost:8000`.

## Public Repo Safety

Use this rule: public repo contains structure, private device contains secrets.

- Keep `.env` private. It is already ignored by git.
- Keep `config/accounts.yaml` private. It is already ignored by git.
- Store API keys, OAuth client secrets, refresh tokens, and access tokens only in `.env` or your shell environment.
- Do not paste screenshots, tokens, or credential JSON into tracked files, issues, or commits.

The app now resolves `${ENV_VAR}` values inside `config/accounts.yaml`, so the file can stay non-sensitive even when you reuse the same template publicly.

## Safe Local Deployment

For the safest free deployment on your own device, run the app bound to `127.0.0.1`. That keeps it reachable only from your laptop.

Plain Python:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Docker:

```bash
docker compose up --build -d
```

The compose file now publishes `127.0.0.1:8000:8000`, so it is not exposed to your local network by default.

## Access From Anywhere Without Exposing Secrets

If you want remote access later, do not expose the app directly to the public internet first.

Safer options:

1. Use Tailscale or another private VPN and keep the app bound to your device.
2. Put a reverse proxy with authentication in front of it.
3. Deploy the API to a private VPS only after moving secrets into server environment variables.

## Required Credentials

### Google Drive

For each Google account you want to scan, you need:

- Google OAuth client ID
- Google OAuth client secret
- Google refresh token with Drive metadata read access

Recommended scope:

- `https://www.googleapis.com/auth/drive.metadata.readonly`

### OneDrive

For each OneDrive account you want to scan, you need either:

- A valid Microsoft Graph access token

or:

- Microsoft app client ID
- Optional client secret if your app type requires it
- Refresh token
- Tenant ID, usually `consumers` for personal Microsoft accounts

Recommended Microsoft Graph permissions:

- `Files.Read`
- `User.Read`
- `offline_access`

### Anthropic

Set `ANTHROPIC_API_KEY` in `.env` to enable AI insight generation.

## API Endpoints

- `GET /api/health`
- `GET /api/storage/summary`
- `GET /api/storage/providers`
- `POST /api/storage/refresh`
- `POST /api/storage/reload-config`
- `POST /api/ai/insights`

## Use From Other Projects

Other apps can query the summary endpoint and consume the response as a standard JSON storage snapshot.

Example:

```bash
curl http://localhost:8000/api/storage/summary
```

## Deploy Anywhere

You can run this on:

- Your Asus laptop directly
- A home server
- A VPS
- Docker on any machine with access to your config and network

If you want your laptop's live local SSD data, the service must run on the laptop or on an agent machine that can inspect that filesystem.

## Continuous Integration

This repository includes GitHub Actions CI in [.github/workflows/ci.yml](.github/workflows/ci.yml).

It runs on every push and pull request to `main` and performs:

- dependency install from `requirements.txt`
- Python compile validation (`python -m compileall app`)
- FastAPI app import smoke check


Add the right non-secret account entries in `config/accounts.yaml`, and store the actual credentials in `.env`.

## Next Step If You Want One Combined Drive

If your actual goal is a single mount point like one giant pooled drive, the pragmatic setup is:

1. Use this project for monitoring, API access, and AI recommendations.
2. Add `rclone` remotes for the Google Drive and OneDrive accounts.
3. Build a union mount on top of those remotes.
4. Let this API monitor the pool and the underlying accounts at the same time.

That gives you both operational visibility and a practical single entry point.
