terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "sa-east-1"
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_ssm_parameter" "api_key" {
  name            = "/projeto-futebol/api-key"
  with_decryption = true 
}