# Deploying DocAssist to a GCP Compute Engine VM

This guide deploys DocAssist to a single Google Compute Engine VM and stores uploaded documents in a **private Google Cloud Storage bucket**.

The deployment uses:

- **Compute Engine** to run the FastAPI application
- **Cloud Storage** for uploaded documents
- **SQLite** on the VM for cases, checklist items, and file references
- A **user-managed service account** so the app can access only the required bucket
- A Linux `systemd` service that runs Uvicorn on **port 80**

The VM configures the application from [`startup-script.sh`](startup-script.sh): it installs Python and Git, clones this repository, installs dependencies, and starts DocAssist automatically.

Docker is not required for this deployment.

---

## Prerequisites

1. A Google account and a GCP project with billing enabled.
2. The **Compute Engine API** enabled for the project.
3. This repository pushed to GitHub:

   ```text
   https://github.com/kumartprem/DocAssist
   ```

4. The repository must include the Cloud Storage version of the application:

   - `storage_backend.py`
   - `google-cloud-storage` in `requirements.txt`
   - `main.py` calling `save_upload(...)`
   - `EnvironmentFile=-/etc/docassist.env` in `deploy/startup-script.sh`

You do not need to install anything on your Windows computer. Use **Google Cloud Shell**, which already has Git and the Google Cloud CLI installed and authenticated.

---

## Step 1 — Open Cloud Shell and clone the repository

1. Open [Google Cloud Console](https://console.cloud.google.com/).
2. Select the GCP project you want to use.
3. Click the **Cloud Shell** icon (`>_`) in the upper-right corner.
4. Run:

```bash
git clone https://github.com/kumartprem/DocAssist.git
cd DocAssist
```

If the folder already exists, update it instead:

```bash
cd ~/DocAssist
git pull origin main
```

Confirm that the correct repository is configured:

```bash
git remote -v
```

The output should show:

```text
https://github.com/kumartprem/DocAssist.git
```

---

## Step 2 — Set the deployment variables

Replace `REPLACE_WITH_YOUR_PROJECT_ID` with the actual GCP Project ID.

```bash
export PROJECT_ID="REPLACE_WITH_YOUR_PROJECT_ID"
export REGION="us-east1"
export ZONE="us-east1-b"
export VM_NAME="docassist-vm"
export SA_NAME="docassist-vm-sa"
export SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
export BUCKET_NAME="docassist-uploads-${PROJECT_ID}"
```

Set the active project and default zone:

```bash
gcloud config set project "$PROJECT_ID"
gcloud config set compute/zone "$ZONE"
```

Confirm the values:

```bash
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Zone: $ZONE"
echo "VM: $VM_NAME"
echo "Service account: $SA_EMAIL"
echo "Bucket: $BUCKET_NAME"
```

Cloud Storage bucket names are globally unique. If the generated name is already taken, change `BUCKET_NAME` to another globally unique name.

---

## Step 3 — Enable the required Google Cloud APIs

```bash
gcloud services enable \
  compute.googleapis.com \
  storage.googleapis.com \
  iam.googleapis.com
```

Confirm that the default VPC network exists:

```bash
gcloud compute networks list
```

You should see a network named `default`.

---

## Step 4 — Verify the Cloud Storage application files

Run these checks from the repository directory:

```bash
grep "google-cloud-storage" requirements.txt
grep "from storage_backend import save_upload" main.py
grep "EnvironmentFile=-/etc/docassist.env" deploy/startup-script.sh
bash -n deploy/startup-script.sh && echo "Startup script syntax is valid"
```

You should see matching output for all three `grep` commands and:

```text
Startup script syntax is valid
```

Do not continue with an older local-storage-only version of the repository.

---

## Step 5 — Create the private Cloud Storage bucket

Create a regional Standard Storage bucket with uniform bucket-level access and public access prevention:

```bash
gcloud storage buckets create "gs://$BUCKET_NAME" \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --default-storage-class=standard \
  --uniform-bucket-level-access \
  --public-access-prevention
```

Verify it:

```bash
gcloud storage buckets describe "gs://$BUCKET_NAME"
```

The bucket must remain private. Users upload through DocAssist; they do not receive direct public access to the bucket.

---

## Step 6 — Create the VM service account

Create a dedicated service account for the DocAssist VM:

```bash
gcloud iam service-accounts create "$SA_NAME" \
  --display-name="DocAssist VM service account"
```

If the service account already exists, the command may return an `already exists` message. Continue using the existing account.

Confirm it:

```bash
gcloud iam service-accounts describe "$SA_EMAIL"
```

The application uses this service account through Compute Engine Application Default Credentials. No downloaded service-account key is required.

---

## Step 7 — Grant the VM access to the bucket

Grant the service account permission to create, read, update, and delete objects in this bucket:

```bash
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET_NAME" \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/storage.objectUser"
```

Verify the bucket IAM policy:

```bash
gcloud storage buckets get-iam-policy "gs://$BUCKET_NAME"
```

Look for:

```text
roles/storage.objectUser
```

and the DocAssist service-account email.

---

## Step 8 — Open the firewall for HTTP port 80

Create a firewall rule that permits incoming HTTP traffic only to VMs carrying the `docassist` network tag:

```bash
gcloud compute firewall-rules create allow-http-docassist \
  --network=default \
  --direction=INGRESS \
  --action=ALLOW \
  --rules=tcp:80 \
  --source-ranges=0.0.0.0/0 \
  --target-tags=docassist \
  --description="Allow public HTTP access to DocAssist"
```

If the rule already exists, verify it instead:

```bash
gcloud compute firewall-rules describe allow-http-docassist
```

---

## Step 9 — Create the Compute Engine VM

Make sure you are inside the cloned repository:

```bash
cd ~/DocAssist
```

Create the VM and attach the dedicated service account:

```bash
gcloud compute instances create "$VM_NAME" \
  --zone="$ZONE" \
  --machine-type=e2-micro \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --boot-disk-type=pd-standard \
  --boot-disk-size=10GB \
  --network=default \
  --tags=docassist \
  --service-account="$SA_EMAIL" \
  --scopes=cloud-platform \
  --metadata-from-file=startup-script=deploy/startup-script.sh
```

The startup script will:

1. Install Python, `pip`, virtual environments, and Git.
2. Clone the repository into `/opt/docassist`.
3. Install `requirements.txt`.
4. Create `/etc/systemd/system/docassist.service`.
5. Start Uvicorn on port 80.

Check the VM:

```bash
gcloud compute instances list
```

The VM should show `RUNNING` and have an external IP address.

---

## Step 10 — Configure the Cloud Storage bucket for the app

Create the systemd environment file on the VM:

```bash
gcloud compute ssh "$VM_NAME" \
  --zone="$ZONE" \
  --command="echo 'GCS_BUCKET=$BUCKET_NAME' | sudo tee /etc/docassist.env >/dev/null && sudo chmod 600 /etc/docassist.env"
```

Reload systemd and restart DocAssist so it starts with the bucket variable:

```bash
gcloud compute ssh "$VM_NAME" \
  --zone="$ZONE" \
  --command="sudo systemctl daemon-reload && sudo systemctl restart docassist.service"
```

This is part of the initial VM configuration. Do not use the application until the verification steps below succeed.

---

## Step 11 — Verify the service and environment

Check the service:

```bash
gcloud compute ssh "$VM_NAME" \
  --zone="$ZONE" \
  --command="sudo systemctl status docassist.service --no-pager"
```

A successful deployment shows:

```text
Active: active (running)
Application startup complete
Uvicorn running on http://0.0.0.0:80
```

Confirm that the service references the environment file:

```bash
gcloud compute ssh "$VM_NAME" \
  --zone="$ZONE" \
  --command="sudo systemctl show docassist.service --property=EnvironmentFiles"
```

Confirm that the running application process received `GCS_BUCKET`:

```bash
gcloud compute ssh "$VM_NAME" \
  --zone="$ZONE" \
  --command="sudo cat /proc/\$(systemctl show -p MainPID --value docassist.service)/environ | tr '\0' '\n' | grep '^GCS_BUCKET='"
```

Expected output:

```text
GCS_BUCKET=YOUR_BUCKET_NAME
```

`systemctl show docassist.service --property=Environment` may appear blank when the value comes from an `EnvironmentFile`. The running-process check above is the reliable verification.

---

## Step 12 — Test Cloud Storage access from the VM

Run a direct upload-and-delete test through the same Python environment used by DocAssist:

```bash
gcloud compute ssh "$VM_NAME" \
  --zone="$ZONE" \
  --command="sudo /opt/docassist/venv/bin/python -c \"from google.cloud import storage; c=storage.Client(); b=c.bucket('$BUCKET_NAME'); x=b.blob('docassist-healthcheck.txt'); x.upload_from_string('Cloud Storage access works'); print('Uploaded:', x.name); x.delete(); print('Deleted test object')\""
```

Expected output:

```text
Uploaded: docassist-healthcheck.txt
Deleted test object
```

If this fails with `403 Forbidden` or `PermissionDenied`, recheck:

- The VM service account
- The `roles/storage.objectUser` bucket binding
- The VM's `cloud-platform` access scope
- The `GCS_BUCKET` value

---

## Step 13 — Get the public IP and open the app

Store the external IP in a variable:

```bash
export EXTERNAL_IP=$(gcloud compute instances describe "$VM_NAME" \
  --zone="$ZONE" \
  --format="get(networkInterfaces[0].accessConfigs[0].natIP)")
```

Display the application link:

```bash
echo "http://$EXTERNAL_IP"
```

Open the printed `http://` link in a browser.

The FastAPI API documentation is available at:

```bash
echo "http://$EXTERNAL_IP/docs"
```

Use HTTP, not HTTPS. HTTPS is not configured by this guide.

---

## Step 14 — Test a complete document upload

1. Open `http://YOUR_EXTERNAL_IP`.
2. Create a test case using fictional information.
3. Add one or more checklist items.
4. Copy the generated client portal link.
5. Open the portal in an Incognito or InPrivate browser window.
6. Upload a sample document.
7. Return to the main dashboard and confirm that the item is marked received.

Confirm that the file was saved in Cloud Storage:

```bash
gcloud storage ls --recursive "gs://$BUCKET_NAME/cases/"
```

Uploaded objects use this structure:

```text
gs://BUCKET_NAME/cases/<case_id>/<checklist_item_id>_<safe_filename>
```

The SQLite database stores a reference such as:

```text
gs://BUCKET_NAME/cases/3/7_passport.pdf
```

The uploaded file should not be written to `/opt/docassist/uploads` when `GCS_BUCKET` is configured correctly.

---

## Step 15 — Operations, updates, backup, and cleanup

### View application logs

```bash
gcloud compute ssh "$VM_NAME" \
  --zone="$ZONE" \
  --command="sudo journalctl -u docassist.service --no-pager -n 100"
```

Follow logs live:

```bash
gcloud compute ssh "$VM_NAME" \
  --zone="$ZONE" \
  --command="sudo journalctl -u docassist.service -f"
```

Press `Ctrl+C` to stop following the logs.

### View startup-script logs

```bash
gcloud compute ssh "$VM_NAME" \
  --zone="$ZONE" \
  --command="sudo journalctl -u google-startup-scripts.service --no-pager -n 150"
```

### Restart the app

```bash
gcloud compute ssh "$VM_NAME" \
  --zone="$ZONE" \
  --command="sudo systemctl restart docassist.service"
```

### Update the app after pushing code to GitHub

```bash
gcloud compute ssh "$VM_NAME" \
  --zone="$ZONE" \
  --command="sudo git -C /opt/docassist fetch origin && sudo git -C /opt/docassist reset --hard origin/main && sudo bash /opt/docassist/deploy/startup-script.sh"
```

The `/etc/docassist.env` file remains on the VM, so the restarted service continues using the configured Cloud Storage bucket.

Verify the service after an update:

```bash
gcloud compute ssh "$VM_NAME" \
  --zone="$ZONE" \
  --command="sudo systemctl status docassist.service --no-pager"
```

### Back up the SQLite database

Uploaded documents are stored in Cloud Storage, but cases and checklist records remain in:

```text
/opt/docassist/docassist.db
```

Create a timestamped backup in Cloud Shell:

```bash
export DB_BACKUP="docassist-db-$(date +%Y%m%d-%H%M%S).db"

gcloud compute ssh "$VM_NAME" \
  --zone="$ZONE" \
  --command="sudo cp /opt/docassist/docassist.db /tmp/$DB_BACKUP && sudo chmod 644 /tmp/$DB_BACKUP"

gcloud compute scp \
  "$VM_NAME:/tmp/$DB_BACKUP" \
  "$HOME/$DB_BACKUP" \
  --zone="$ZONE"
```

Optionally copy that database backup into the private bucket:

```bash
gcloud storage cp "$HOME/$DB_BACKUP" "gs://$BUCKET_NAME/backups/$DB_BACKUP"
```

### Stop and start the VM

Stop:

```bash
gcloud compute instances stop "$VM_NAME" --zone="$ZONE"
```

Start:

```bash
gcloud compute instances start "$VM_NAME" --zone="$ZONE"
```

The external IP may change after stopping and restarting the VM unless a static IP is reserved. Retrieve the link again using Step 13.

### Delete the deployment

Delete the VM:

```bash
gcloud compute instances delete "$VM_NAME" --zone="$ZONE"
```

Deleting the VM normally deletes its boot disk and therefore deletes `docassist.db`. It does **not** automatically delete the Cloud Storage bucket or its uploaded objects.

Delete the firewall rule:

```bash
gcloud compute firewall-rules delete allow-http-docassist
```

Delete the bucket only when you intentionally want to remove every uploaded document and backup in it:

```bash
gcloud storage rm --recursive "gs://$BUCKET_NAME/**"
gcloud storage buckets delete "gs://$BUCKET_NAME"
```

Delete the service account if it is no longer needed:

```bash
gcloud iam service-accounts delete "$SA_EMAIL"
```

---

## Data locations

| Data | Storage location |
|---|---|
| Application source | `/opt/docassist` on the VM |
| Python environment | `/opt/docassist/venv` on the VM |
| Cases and checklist records | `/opt/docassist/docassist.db` on the VM |
| Uploaded documents | `gs://BUCKET_NAME/cases/` in private Cloud Storage |
| Bucket configuration | `/etc/docassist.env` on the VM |
| Application logs | `journalctl -u docassist.service` |

---

## Cost notes

An `e2-micro` VM and standard persistent disk in an eligible US region may qualify for Google Cloud Free Tier allowances when usage remains within current limits. Cloud Storage, network egress, external IPv4 addresses, static IP addresses, and usage above free allowances can generate charges.

Always check the current pricing and Free Tier documentation before leaving resources running:

- [Google Cloud Free Program](https://cloud.google.com/free/docs/free-cloud-features)
- [Compute Engine pricing](https://cloud.google.com/compute/vm-instance-pricing)
- [Cloud Storage pricing](https://cloud.google.com/storage/pricing)

---

## Security and architecture limitations

- The Cloud Storage bucket is private and is accessed through the VM service account.
- The lawyer dashboard is currently unauthenticated.
- The app is served over plain HTTP, not HTTPS.
- Anyone who knows the public VM IP may be able to access the dashboard.
- SQLite remains tied to the VM boot disk unless it is backed up or moved to a managed database.
- Deleting a case or checklist record does not necessarily delete its corresponding Cloud Storage object unless the application explicitly implements that cleanup.

This deployment is suitable for development, coursework, and demonstrations. Do not use real client PII or confidential legal documents until authentication, HTTPS, authorization, audit logging, file validation, malware scanning, and a production database strategy are implemented.

---

## Relevant Google Cloud documentation

- [Use startup scripts on Linux VMs](https://cloud.google.com/compute/docs/instances/startup-scripts/linux)
- [Create a VM with a user-managed service account](https://cloud.google.com/compute/docs/access/create-enable-service-accounts-for-instances)
- [Cloud Storage bucket creation](https://cloud.google.com/storage/docs/creating-buckets)
- [Uniform bucket-level access](https://cloud.google.com/storage/docs/uniform-bucket-level-access)
- [Public access prevention](https://cloud.google.com/storage/docs/public-access-prevention)
- [Cloud Storage IAM roles](https://cloud.google.com/storage/docs/access-control/iam-roles)
