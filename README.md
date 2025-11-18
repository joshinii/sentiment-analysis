Sentiment Analysis Platform

A serverless sentiment analysis application using AWS Lambda, API Gateway, DynamoDB, and S3.
Analyzes text to determine if it's positive or negative using AI. You can:
- Analyze single texts in real-time
- Process multiple texts in batch mode
- View your analysis history


Deployment Steps:

Prerequisites

Before you start, make sure you have:
- An AWS account
- AWS CLI installed on your computer
- Terraform installed 
- Python 3.11 or higher

Step 1: Set Up AWS Credentials

Open your terminal and run:

```bash
aws configure
```

Step 2: Configure Your Email for Alerts

Go to the infrastructure folder:

```bash
cd sentiment-analysis-infrastructure
```

Copy the example config file:

```bash
cp terraform.tfvars.example terraform.tfvars
```

Open `terraform.tfvars` in any text editor and change this line:

```hcl
alert_email = "xxx@xx.com"  # Put YOUR real email here
```

Save the file. You'll get email alerts if anything goes wrong with your app.


Step 3: Deploy the Infrastructure

Still in the `sentiment-analysis-infrastructure` folder, run:

```bash
terraform init

terraform plan

terraform apply
```

Step 4: Upload Lambda Function Code

Now we need to upload the actual code for our functions.

For the Sentiment Analyzer:

```bash
cd ../backend/sentiment_analyzer

 Create a package folder
mkdir package

 Install the libraries the code needs
pip install -r requirements.txt -t package/ --platform manylinux2014_x86_64 --only-binary=:all:

 Copy our code
cp lambda_function.py package/

 Zip it up
cd package
zip -r ../sentiment_analyzer.zip .
cd ..

 Upload to AWS
aws lambda update-function-code \
  --function-name sentiment-platform-dev-analyze-sentiment \
  --zip-file fileb://sentiment_analyzer.zip
```

For the Batch Processor:

```bash
cd ../batch_processor

mkdir package
pip install -r requirements.txt -t package/
cp batch_handler.py package/
cd package && zip -r ../batch_processor.zip . && cd ..

aws lambda update-function-code \
  --function-name sentiment-platform-dev-batch-processor \
  --zip-file fileb://batch_processor.zip
```

For the History Handler:

```bash
cd ../history

mkdir package
pip install -r requirements.txt -t package/
cp history_handler.py package/
cd package && zip -r ../history.zip . && cd ..

aws lambda update-function-code \
  --function-name sentiment-platform-dev-history \
  --zip-file fileb://history.zip
```

Step 5: Update and Upload the Frontend

Go to the frontend folder:

```bash
cd ../../frontend
```

Open `index.html` in a text editor and find this line (around line 20):

```javascript
const apiUrl = 'http://localhost:5000';
```

Replace it with your actual API endpoint from Step 3's output:

```javascript
const apiUrl = 'https://YOUR-API-ID.execute-api.us-east-1.amazonaws.com/dev';
```

Save the file.

Now upload it to AWS:

```bash
 Get your bucket name (from Step 3 outputs)
cd ../sentiment-analysis-infrastructure
terraform output frontend_bucket

 Upload the file
cd ../frontend
aws s3 cp index.html s3://YOUR-BUCKET-NAME/
```

Replace `YOUR-BUCKET-NAME` with the actual bucket name from the output.


Step 6: Clear the CloudFront Cache

Your website is served through CloudFront (a CDN). We need to tell it about the new file:

```bash
cd ../sentiment-analysis-infrastructure
terraform output cloudfront_distribution_id

aws cloudfront create-invalidation \
  --distribution-id YOUR-DISTRIBUTION-ID \
  --paths "/*"
```

This takes 10-15 minutes to propagate globally.


Step 7: Confirm Your Email Subscription

Check your email! You should have received a message from AWS asking you to confirm your subscription to alerts.

Click the confirmation link in that email. Without this, you won't get error notifications.


Step 8: Test Your Application

Get your CloudFront URL:

```bash
cd sentiment-analysis-infrastructure
terraform output cloudfront_url
```

Open that URL in your browser!


Cleanup (When You're Done)

To delete everything and stop charges:

```bash
cd sentiment-analysis-infrastructure
terraform destroy
```

Type `yes` when asked. This removes everything from AWS.

Warning: This deletes all your data permanently!
