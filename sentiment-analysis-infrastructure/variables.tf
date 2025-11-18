variable "project_name" {
  description = "Name of the project"
  type        = string
  default     = "sentiment-platform"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-west-2"
}

variable "alert_email" {
  description = "Email address for CloudWatch alerts"
  type        = string
}

variable "tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default = {
    Project     = "SentimentAnalysis"
    ManagedBy   = "Terraform"
    Environment = "Development"
  }
}
