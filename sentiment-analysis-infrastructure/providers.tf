provider "aws" {
  region = var.aws_region

  default_tags {
    tags = var.tags
  }
}

# Data sources
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# Random String for Unique Naming
resource "random_string" "suffix" {
  length  = 8
  special = false
  upper   = false
}
