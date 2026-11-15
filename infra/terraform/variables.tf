variable "vercel_team_id" {
  type = string
}

variable "vercel_project_id" {
  type = string
}

variable "supabase_organization_id" {
  type = string
}

variable "supabase_region" {
  type = string
}

variable "github_owner" {
  type = string
}

variable "github_repository" {
  type = string
}

variable "admin_email" {
  type = string
}

variable "supabase_access_token" {
  type      = string
  sensitive = true
}

variable "supabase_db_password" {
  type      = string
  sensitive = true
}

variable "anthropic_api_key" {
  type      = string
  sensitive = true
}

variable "resend_api_key" {
  type      = string
  sensitive = true
  default   = null
}

variable "sentry_dsn_agent" {
  type    = string
  default = null
}

variable "sentry_dsn_web" {
  type    = string
  default = null
}

variable "healthcheck_refresh_url" {
  type      = string
  sensitive = true
  default   = null
}

variable "healthcheck_evals_url" {
  type      = string
  sensitive = true
  default   = null
}
