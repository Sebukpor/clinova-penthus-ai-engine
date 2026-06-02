# ============================================
# Clinova Penthus AI Engine - OCI Infrastructure
# Terraform configuration for OCI deployment
# ============================================

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = ">= 5.0.0"
    }
  }

  backend "s3" {
    bucket   = "clinova-terraform-state"
    key      = "penthus/oci.tfstate"
    region   = "us-ashburn-1"
    endpoint = "https://namespace.compat.objectstorage.us-ashburn-1.oraclecloud.com"

    skip_region_validation      = true
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    force_path_style            = true
  }
}

provider "oci" {
  tenancy_ocid     = var.tenancy_ocid
  region           = var.region
  user_ocid        = var.user_ocid
  fingerprint      = var.fingerprint
  private_key_path = var.private_key_path
}

# Variables
variable "tenancy_ocid" {
  description = "OCI Tenancy OCID"
  type        = string
}

variable "region" {
  description = "OCI Region"
  type        = string
  default     = "us-ashburn-1"
}

variable "compartment_ocid" {
  description = "Compartment OCID"
  type        = string
}

variable "user_ocid" {
  description = "User OCID"
  type        = string
  default     = ""
}

variable "fingerprint" {
  description = "API Key Fingerprint"
  type        = string
  default     = ""
}

variable "private_key_path" {
  description = "Private Key Path"
  type        = string
  default     = ""
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production"
}

# Local values
locals {
  project_name = "clinova-penthus"
  common_tags = {
    Project     = "Clinova"
    Component   = "Penthus-AI-Engine"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# OCI Container Registry
resource "oci_artifacts_container_repository" "penthus_api" {
  compartment_id = var.compartment_ocid
  display_name   = "clinova/penthus-api"
  is_public      = false
  is_immutable   = false

  freeform_tags = local.common_tags
}

resource "oci_artifacts_container_repository" "penthus_vllm" {
  compartment_id = var.compartment_ocid
  display_name   = "clinova/penthus-vllm"
  is_public      = false
  is_immutable   = false

  freeform_tags = local.common_tags
}

# OCI Object Storage - Documents
resource "oci_objectstorage_bucket" "documents" {
  compartment_id = var.compartment_ocid
  name           = "clinova-documents-${var.environment}"
  namespace      = data.oci_objectstorage_namespace.ns.namespace
  storage_tier   = "Standard"
  access_type    = "NoPublicAccess"

  freeform_tags = local.common_tags
}

# OCI Object Storage - Model Artifacts
resource "oci_objectstorage_bucket" "models" {
  compartment_id = var.compartment_ocid
  name           = "clinova-models-${var.environment}"
  namespace      = data.oci_objectstorage_namespace.ns.namespace
  storage_tier   = "Standard"
  access_type    = "NoPublicAccess"

  freeform_tags = local.common_tags
}

# OCI Vault
resource "oci_kms_vault" "penthus" {
  compartment_id = var.compartment_ocid
  display_name   = "clinova-penthus-${var.environment}"
  vault_type     = "DEFAULT"

  freeform_tags = local.common_tags
}

# Vault Key
resource "oci_kms_key" "penthus_master" {
  compartment_id = var.compartment_ocid
  display_name   = "penthus-master-key"
  key_shape {
    algorithm = "AES"
    length    = 32
  }
  management_endpoint = oci_kms_vault.penthus.management_endpoint

  freeform_tags = local.common_tags
}

# Secrets
resource "oci_vault_secret" "db_password" {
  compartment_id = var.compartment_ocid
  vault_id       = oci_kms_vault.penthus.id
  key_id         = oci_kms_key.penthus_master.id
  secret_name    = "penthus-db-password"
  secret_content {
    content_type = "Base64"
    content      = base64encode(var.db_password)
  }
}

resource "oci_vault_secret" "hf_token" {
  compartment_id = var.compartment_ocid
  vault_id       = oci_kms_vault.penthus.id
  key_id         = oci_kms_key.penthus_master.id
  secret_name    = "penthus-hf-token"
  secret_content {
    content_type = "Base64"
    content      = base64encode(var.hf_token)
  }
}

resource "oci_vault_secret" "secret_key" {
  compartment_id = var.compartment_ocid
  vault_id       = oci_kms_vault.penthus.id
  key_id         = oci_kms_key.penthus_master.id
  secret_name    = "penthus-secret-key"
  secret_content {
    content_type = "Base64"
    content      = base64encode(var.app_secret_key)
  }
}

# Data sources
data "oci_objectstorage_namespace" "ns" {
  compartment_id = var.compartment_ocid
}

# Variables for secrets
variable "db_password" {
  description = "PostgreSQL password"
  type        = string
  sensitive   = true
}

variable "hf_token" {
  description = "Hugging Face token"
  type        = string
  sensitive   = true
}

variable "app_secret_key" {
  description = "Application secret key"
  type        = string
  sensitive   = true
}

# Outputs
output "oke_cluster_id" {
  value = oci_containerengine_cluster.penthus.id
}

output "container_registry_api" {
  value = "${data.oci_objectstorage_namespace.ns.namespace}.ocir.io/${data.oci_identity_tenancy.tenancy.name}/clinova/penthus-api"
}

output "container_registry_vllm" {
  value = "${data.oci_objectstorage_namespace.ns.namespace}.ocir.io/${data.oci_identity_tenancy.tenancy.name}/clinova/penthus-vllm"
}

output "vault_ocid" {
  value = oci_kms_vault.penthus.id
}

# Data sources for outputs
data "oci_identity_tenancy" "tenancy" {
  tenancy_id = var.tenancy_ocid
}
