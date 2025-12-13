# Sentiment Analysis Platform

A serverless sentiment analysis application using **AWS Lambda, API Gateway, DynamoDB, and S3**. 
It uses AI to determine if text is positive or negative.

**Features:**
-   Real-time single text analysis
-   Batch CSV processing
-   History tracking
-   Fully automated deployment

## Prerequisites
-   **AWS Account** with CLI configured (`aws configure`)
-   **Terraform** installed
-   **Python 3.11+** installed

## Deployment

### 1. Configure Email Alerts
1.  Go to `sentiment-analysis-infrastructure`.
2.  Copy example config:
    ```bash
    cp terraform.tfvars.example terraform.tfvars
    ```
3.  Edit `terraform.tfvars` and add your email for alerts.

### 2. Provision Infrastructure
Run Terraform to create the AWS resources:
```bash
cd sentiment-analysis-infrastructure
terraform init
terraform apply
```
Type `yes` to confirm.

### 3. Sync Configuration
Update your local config with the new AWS IDs:
```bash
# Go back to root directory
cd .. 
python update_config.py
```

### 4. Build & Deploy Code
Run the master script to package code, upload assets, and update the frontend:
```bash
python deploy_all.py
```
**That's it!** The script will output your **CloudFront URL** at the end.

---

## Local Development
You can run the backend locally for testing:
1.  Install dependencies:
    ```bash
    pip install -r backend/sentiment_analyzer/requirements.txt
    ```
2.  Run the local server:
    ```bash
    python local_server.py
    ```
3.  Open `frontend/index.html` in your browser and select "Local Testing" mode.

---

## Cleanup
To destroy all resources and stop charges:
```bash
cd sentiment-analysis-infrastructure
terraform destroy
```
*(Note: S3 buckets are forced to empty themselves before deletion, so no manual cleanup is needed.)*
