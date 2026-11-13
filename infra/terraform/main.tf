terraform {
  required_version = ">= 1.11"

  cloud {
    organization = "ernesto-reyes-dev-org"

    workspaces {
      name = "job-scout-production"
    }
  }

  required_providers {
    vercel = {
      source  = "vercel/vercel"
      version = "~> 5.26"
    }
    supabase = {
      source  = "supabase/supabase"
      version = "~> 1.11"
    }
    github = {
      source  = "integrations/github"
      version = "~> 6.13"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.7"
    }
  }
}

# Reads VERCEL_API_TOKEN from the workspace's environment.
provider "vercel" {}

provider "supabase" {
  access_token = var.supabase_access_token
}

# Reads GITHUB_TOKEN from the workspace's environment.
provider "github" {
  owner = var.github_owner
}
