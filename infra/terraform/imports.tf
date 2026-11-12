import {
  to = supabase_project.production
  id = "epvfupppjzvgaqqrijvf"
}

import {
  to = supabase_settings.production
  id = "epvfupppjzvgaqqrijvf"
}

import {
  for_each = toset(["SUPABASE_ACCESS_TOKEN", "SUPABASE_DB_PASSWORD", "SUPABASE_PROJECT_ID"])
  to       = github_actions_secret.repository[each.key]
  id       = "job-finder:${each.key}"
}

import {
  for_each = {
    SUPABASE_URL                  = "sAjSHoF6D7HsxMDJ"
    SUPABASE_ANON_KEY             = "fwg5xUfmpwRceNep"
    SUPABASE_SERVICE_ROLE_KEY     = "kkedCwfNHSjRSa9g"
    NEXT_PUBLIC_SUPABASE_URL      = "r0ZoFxOBRYR6rvgd"
    NEXT_PUBLIC_SUPABASE_ANON_KEY = "VZr4W6mTyNbcn1fS"
    ANTHROPIC_API_KEY             = "7ebeJGgVBAOZTsqj"
    CRON_SECRET                   = "39NUa6BZ6SPsrhFR"
    ADMIN_EMAIL                   = "zrB2RETaRZwowiYP"
  }
  to = vercel_project_environment_variable.production[each.key]
  id = "${var.vercel_team_id}/${var.vercel_project_id}/${each.value}"
}
