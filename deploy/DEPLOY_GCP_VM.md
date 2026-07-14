# Deploying DocAssist to a GCP Compute Engine VM

This is the **simplest** way to run DocAssist on Google Cloud: a single small VM that runs
the app exactly as-is (SQLite + local `uploads/`). **No code changes.** An `e2-micro`
instance in a US region is **Free-Tier eligible**.

The VM configures itself on boot using [`startup-script.sh`](startup-script.sh): it installs
Python, clones this repo from GitHub, installs dependencies, and starts the app as a
`systemd` service on **port 80**.

---

## Prerequisites

1. A **Google account** and a **GCP project with billing enabled**
   (https://console.cloud.google.com — create a project, then link a billing account).
2. This repository pushed to GitHub (already done: `github.com/Bisht9887/DocAssist`).
   Make sure the latest commit — including the `deploy/` folder — is pushed.

You do **not** need to install anything locally: use **Google Cloud Shell** (a browser
terminal with `gcloud` pre-installed and already authenticated).

---

## Step 1 — Open Cloud Shell and get the code

1. Go to https://console.cloud.google.com and select your project.
2. Click the **Cloud Shell** icon (`>_`) in the top-right toolbar.
3. In the Cloud Shell terminal, clone the repo (this gives Cloud Shell access to the
   startup script):

```bash
git clone https://github.com/Bisht9887/DocAssist.git
cd DocAssist
```

## Step 2 — Set your project and zone

Free-Tier eligible zones are in `us-west1`, `us-central1`, and `us-east1`.

```bash
export PROJECT_ID="REPLACE_WITH_YOUR_PROJECT_ID"
export ZONE="us-central1-a"

gcloud config set project "$PROJECT_ID"
gcloud services enable compute.googleapis.com
```

## Step 3 — Open the firewall for HTTP (port 80)

```bash
gcloud compute firewall-rules create allow-http-docassist \
  --allow=tcp:80 \
  --target-tags=docassist \
  --description="Allow inbound HTTP to DocAssist"
```

## Step 4 — Create the VM (auto-deploys via the startup script)

```bash
gcloud compute instances create docassist-vm \
  --zone="$ZONE" \
  --machine-type=e2-micro \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --tags=docassist \
  --metadata-from-file=startup-script=deploy/startup-script.sh
```

The VM boots and runs the startup script automatically. First-time setup (apt install +
pip install) typically takes **2–4 minutes**.

## Step 5 — Get the public IP and open the app

```bash
gcloud compute instances describe docassist-vm --zone="$ZONE" \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)'
```

Open **`http://<THAT_IP>`** in a browser → the Lawyer Dashboard.
Client portal links the app generates will automatically use this same IP.

> Give it a couple of minutes after creation; if the page doesn't load yet, the startup
> script is probably still installing. Check progress in Step 6.

---

## Step 6 — Verify / troubleshoot

SSH into the VM from Cloud Shell:

```bash
gcloud compute ssh docassist-vm --zone="$ZONE"
```

Then, on the VM:

```bash
# Was the startup script successful?
sudo journalctl -u google-startup-scripts.service --no-pager | tail -30

# Is the app running?
sudo systemctl status docassist.service

# App logs (live)
sudo journalctl -u docassist.service -f

# Restart the app manually if needed
sudo systemctl restart docassist.service
```

---

## Updating the app after a code change

Push your changes to GitHub, then redeploy by either:

**A) Re-running the startup logic** (simplest):

```bash
gcloud compute ssh docassist-vm --zone="$ZONE" --command="sudo google_metadata_script_runner startup"
```

**B) Manually on the VM:**

```bash
gcloud compute ssh docassist-vm --zone="$ZONE"
cd /opt/docassist && sudo git pull
sudo ./venv/bin/pip install -r requirements.txt
sudo systemctl restart docassist.service
```

---

## Cost & cleanup

- **Cost:** one `e2-micro` in a US free-tier region + 30 GB standard disk is within the
  **Always Free** tier. A static IP or exceeding free limits may incur small charges.
- **Stop the VM** (keeps disk, stops compute billing):

  ```bash
  gcloud compute instances stop docassist-vm --zone="$ZONE"
  ```

- **Delete everything** when done:

  ```bash
  gcloud compute instances delete docassist-vm --zone="$ZONE"
  gcloud compute firewall-rules delete allow-http-docassist
  ```

---

## Notes & limitations

- **Data lives on the VM's disk.** SQLite (`docassist.db`) and uploaded files persist across
  reboots but are tied to this one VM. Deleting the VM (without keeping the disk) deletes the
  data. Enable disk snapshots if you need backups.
- **Fresh database:** the app creates its tables on first start, so the VM begins with an
  empty case list. To carry over your local demo data, copy the DB up after Step 5:

  ```bash
  gcloud compute scp docassist.db docassist-vm:/opt/docassist/docassist.db --zone="$ZONE"
  gcloud compute ssh docassist-vm --zone="$ZONE" --command="sudo systemctl restart docassist.service"
  ```

- **HTTP only.** This setup serves plain HTTP on port 80. For HTTPS/a custom domain, put the
  VM behind an HTTPS Load Balancer or add a reverse proxy (nginx + Let's Encrypt) — or use the
  Cloud Run path in [`../ARCHITECTURE.md`](../ARCHITECTURE.md) §10.
- **Security:** the dashboard is unauthenticated (see ARCHITECTURE.md §9). Don't put real
  client PII on a public demo VM.
