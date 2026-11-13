resource "supabase_project" "production" {
  organization_id   = var.supabase_organization_id
  name              = "job-scout"
  region            = var.supabase_region
  database_password = var.supabase_db_password

  lifecycle {
    prevent_destroy = true
    # The API never returns the password, and resizing happens in the dashboard.
    ignore_changes = [database_password, instance_size]
  }
}

data "supabase_apikeys" "production" {
  project_ref = supabase_project.production.id
}

resource "supabase_settings" "production" {
  project_ref = supabase_project.production.id

  auth = jsonencode({
    site_url       = "https://job-role-scout-ai.vercel.app"
    uri_allow_list = "https://job-role-scout-ai.vercel.app/auth/callback"
  })

  lifecycle {
    prevent_destroy = true
  }
}

locals {
  supabase_url = "https://${supabase_project.production.id}.supabase.co"
}
