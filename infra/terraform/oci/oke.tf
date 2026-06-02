# ============================================
# Clinova Penthus AI Engine - OKE Cluster
# Oracle Kubernetes Engine configuration
# ============================================

resource "oci_containerengine_cluster" "penthus" {
  compartment_id     = var.compartment_ocid
  kubernetes_version = "v1.29.1"
  name               = "clinova-penthus-${var.environment}"
  vcn_id             = oci_core_vcn.penthus.id
  endpoint_config {
    is_public_ip_enabled = false
    subnet_id            = oci_core_subnet.private_app.id
  }
  options {
    add_ons {
      is_kubernetes_dashboard_enabled = false
      is_tiller_enabled               = false
    }
    admission_controller_options {
      is_pod_security_policy_enabled = true
    }
    kubernetes_network_config {
      pods_cidr     = "10.244.0.0/16"
      services_cidr = "10.96.0.0/16"
    }
    service_lb_subnet_ids = [oci_core_subnet.public_lb.id]
  }

  freeform_tags = local.common_tags
}

# CPU Node Pool
resource "oci_containerengine_node_pool" "cpu" {
  cluster_id         = oci_containerengine_cluster.penthus.id
  compartment_id     = var.compartment_ocid
  kubernetes_version = "v1.29.1"
  name               = "cpu-pool"
  node_shape         = "VM.Standard.E4.Flex"
  node_shape_config {
    ocpus         = 4
    memory_in_gbs = 16
  }
  node_config_details {
    placement_configs {
      availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
      subnet_id           = oci_core_subnet.private_app.id
    }
    size = 3
    node_pool_pod_network_option_details {
      cni_type          = "FLANNEL_OVERLAY"
      max_pods_per_node = 110
    }
  }
  initial_node_labels {
    key   = "node-type"
    value = "cpu"
  }
  initial_node_labels {
    key   = "app"
    value = "clinova-api"
  }

  freeform_tags = local.common_tags
}

# GPU Node Pool
resource "oci_containerengine_node_pool" "gpu" {
  cluster_id         = oci_containerengine_cluster.penthus.id
  compartment_id     = var.compartment_ocid
  kubernetes_version = "v1.29.1"
  name               = "gpu-pool"
  node_shape         = "VM.GPU.A10.1"
  node_shape_config {
    ocpus         = 15
    memory_in_gbs = 240
  }
  node_config_details {
    placement_configs {
      availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
      subnet_id           = oci_core_subnet.private_gpu.id
    }
    size = 2
    node_pool_pod_network_option_details {
      cni_type          = "FLANNEL_OVERLAY"
      max_pods_per_node = 30
    }
  }
  initial_node_labels {
    key   = "node-type"
    value = "gpu"
  }
  initial_node_labels {
    key   = "app"
    value = "penthus-vllm"
  }
  initial_node_labels {
    key   = "nvidia.com/gpu"
    value = "true"
  }

  freeform_tags = local.common_tags
}

# Kubernetes provider for post-cluster resources
provider "kubernetes" {
  host                   = oci_containerengine_cluster.penthus.endpoints[0].private_endpoint
  cluster_ca_certificate = base64decode(oci_containerengine_cluster.penthus.kube_config[0]."cluster_ca_certificate")
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "oci"
    args        = ["ce", "cluster", "generate-token", "--cluster-id", oci_containerengine_cluster.penthus.id, "--region", var.region]
  }
}

# Create namespace
resource "kubernetes_namespace" "clinova" {
  metadata {
    name = "clinova"
    labels = {
      "istio-injection" = "disabled"
    }
  }
}

# Data sources
data "oci_identity_availability_domains" "ads" {
  compartment_id = var.compartment_ocid
}

# Outputs
output "oke_endpoint" {
  value     = oci_containerengine_cluster.penthus.endpoints[0].private_endpoint
  sensitive = true
}

output "cpu_node_pool_id" {
  value = oci_containerengine_node_pool.cpu.id
}

output "gpu_node_pool_id" {
  value = oci_containerengine_node_pool.gpu.id
}
