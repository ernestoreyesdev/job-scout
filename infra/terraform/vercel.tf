locals {
  supabase_secret_key = one([for key in data.supabase_apikeys.production.secret_keys : key.api_key if key.name == "default"])

  production_and_preview = ["production", "preview"]
  production             = ["production"]

  vercel_variables = merge(
    {
      SUPABASE_URL                  = { value = local.supabase_url, sensitive = false, target = local.production_and_preview }
      SUPABASE_ANON_KEY             = { value = data.supabase_apikeys.production.publishable_key, sensitive = false, target = local.production_and_preview }
      SUPABASE_SERVICE_ROLE_KEY     = { value = local.supabase_secret_key, sensitive = true, target = local.production_and_preview }
      NEXT_PUBLIC_SUPABASE_URL      = { value = local.supabase_url, sensitive = false, target = local.production_and_preview }
      NEXT_PUBLIC_SUPABASE_ANON_KEY = { value = data.supabase_apikeys.production.publishable_key, sensitive = false, target = local.production_and_preview }
      ANTHROPIC_API_KEY             = { value = var.anthropic_api_key, sensitive = true, target = local.production }
      ADMIN_EMAIL                   = { value = var.admin_email, sensitive = false, target = local.production }
    },
    nonsensitive(var.resend_api_key == null) ? {} : { RESEND_API_KEY = { value = var.resend_api_key, sensitive = true, target = local.production } },
  )
}

resource "vercel_project_environment_variable" "production" {
  for_each = toset(keys(local.vercel_variables))

  team_id    = var.vercel_team_id
  project_id = var.vercel_project_id
  key        = each.key
  value      = local.vercel_variables[each.key].value
  sensitive  = local.vercel_variables[each.key].sensitive
  target     = local.vercel_variables[each.key].target
}
