locals {
  github_secrets = merge(
    {
      ADMIN_EMAIL               = var.admin_email
      ANTHROPIC_API_KEY         = var.anthropic_api_key
      SUPABASE_ACCESS_TOKEN     = var.supabase_access_token
      SUPABASE_DB_PASSWORD      = var.supabase_db_password
      SUPABASE_PROJECT_ID       = supabase_project.production.id
      SUPABASE_SERVICE_ROLE_KEY = local.supabase_secret_key
      SUPABASE_URL              = local.supabase_url
    },
    nonsensitive(var.resend_api_key == null) ? {} : { RESEND_API_KEY = var.resend_api_key },
    var.sentry_dsn_agent == null ? {} : { SENTRY_DSN = var.sentry_dsn_agent },
    nonsensitive(var.healthcheck_refresh_url == null) ? {} : { HEALTHCHECK_REFRESH_URL = var.healthcheck_refresh_url },
    nonsensitive(var.healthcheck_evals_url == null) ? {} : { HEALTHCHECK_EVALS_URL = var.healthcheck_evals_url },
  )
}

resource "github_actions_secret" "repository" {
  for_each = toset(keys(local.github_secrets))

  repository  = var.github_repository
  secret_name = each.key
  value       = local.github_secrets[each.key]
}
