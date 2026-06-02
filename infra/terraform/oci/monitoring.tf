# ============================================
# Clinova Penthus AI Engine - OCI Monitoring
# Alarms, notifications, and logging configuration
# ============================================

# Log Group
resource "oci_logging_log_group" "penthus" {
  compartment_id = var.compartment_ocid
  display_name   = "clinova-penthus-${var.environment}"

  freeform_tags = local.common_tags
}

# API Log
resource "oci_logging_log" "api" {
  display_name = "penthus-api-log"
  log_group_id = oci_logging_log_group.penthus.id
  log_type     = "SERVICE"
  configuration {
    source {
      category    = "all"
      resource    = kubernetes_namespace.clinova.metadata[0].name
      service     = "oke"
      source_type = "OCISERVICE"
    }
    compartment_id = var.compartment_ocid
  }
  is_enabled = true
  retention_duration = 30
}

# Notification Topic
resource "oci_ons_notification_topic" "penthus" {
  compartment_id = var.compartment_ocid
  name           = "clinova-penthus-alerts"

  freeform_tags = local.common_tags
}

# Alarm - High Error Rate
resource "oci_monitoring_alarm" "high_error_rate" {
  compartment_id        = var.compartment_ocid
  destinations          = [oci_ons_notification_topic.penthus.id]
  display_name          = "Penthus-HighErrorRate"
  is_enabled            = true
  metric_compartment_id = var.compartment_ocid
  namespace             = "clinova_penthus"
  query                 = "Errors[5m].sum() > 10"
  severity              = "CRITICAL"
  body                  = "High error rate detected in Penthus AI Engine"

  freeform_tags = local.common_tags
}

# Alarm - vLLM High Latency
resource "oci_monitoring_alarm" "vllm_high_latency" {
  compartment_id        = var.compartment_ocid
  destinations          = [oci_ons_notification_topic.penthus.id]
  display_name          = "Penthus-vLLMHighLatency"
  is_enabled            = true
  metric_compartment_id = var.compartment_ocid
  namespace             = "clinova_penthus"
  query                 = "vllm_latency[5m].mean() > 5000"
  severity              = "WARNING"
  body                  = "vLLM inference latency exceeds 5 seconds"

  freeform_tags = local.common_tags
}

# Alarm - GPU Memory
resource "oci_monitoring_alarm" "gpu_memory" {
  compartment_id        = var.compartment_ocid
  destinations          = [oci_ons_notification_topic.penthus.id]
  display_name          = "Penthus-GPUMemoryHigh"
  is_enabled            = true
  metric_compartment_id = var.compartment_ocid
  namespace             = "oci_oke"
  query                 = "GpuMemoryUtilization[5m].mean() > 85"
  severity              = "WARNING"
  body                  = "GPU memory utilization above 85%"

  freeform_tags = local.common_tags
}

# Alarm - Pod Restarts
resource "oci_monitoring_alarm" "pod_restarts" {
  compartment_id        = var.compartment_ocid
  destinations          = [oci_ons_notification_topic.penthus.id]
  display_name          = "Penthus-PodRestartHigh"
  is_enabled            = true
  metric_compartment_id = var.compartment_ocid
  namespace             = "oci_oke"
  query                 = "PodRestartCount[10m].sum() > 5"
  severity              = "WARNING"
  body                  = "High pod restart count detected"

  freeform_tags = local.common_tags
}

# Outputs
output "notification_topic_ocid" {
  value = oci_ons_notification_topic.penthus.id
}

output "log_group_ocid" {
  value = oci_logging_log_group.penthus.id
}
