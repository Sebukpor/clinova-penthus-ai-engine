# ============================================
# Clinova Penthus AI Engine - OCI Network
# VCN, subnets, security lists, and NSGs
# ============================================

resource "oci_core_vcn" "penthus" {
  compartment_id = var.compartment_ocid
  cidr_block     = "10.0.0.0/16"
  display_name   = "clinova-penthus-vcn"
  dns_label      = "clinovapenthus"

  freeform_tags = local.common_tags
}

# Internet Gateway
resource "oci_core_internet_gateway" "igw" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.penthus.id
  display_name   = "penthus-igw"
  enabled        = true

  freeform_tags = local.common_tags
}

# NAT Gateway
resource "oci_core_nat_gateway" "nat" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.penthus.id
  display_name   = "penthus-nat"

  freeform_tags = local.common_tags
}

# Service Gateway
resource "oci_core_service_gateway" "sgw" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.penthus.id
  display_name   = "penthus-sgw"
  services {
    service_id = data.oci_core_services.all.services[0].id
  }

  freeform_tags = local.common_tags
}

# Route Table - Public
resource "oci_core_route_table" "public" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.penthus.id
  display_name   = "penthus-public-rt"

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.igw.id
  }

  freeform_tags = local.common_tags
}

# Route Table - Private
resource "oci_core_route_table" "private" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.penthus.id
  display_name   = "penthus-private-rt"

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_nat_gateway.nat.id
  }

  route_rules {
    destination       = data.oci_core_services.all.services[0].cidr_block
    destination_type  = "SERVICE_CIDR_BLOCK"
    network_entity_id = oci_core_service_gateway.sgw.id
  }

  freeform_tags = local.common_tags
}

# Public Subnet - Load Balancer
resource "oci_core_subnet" "public_lb" {
  compartment_id    = var.compartment_ocid
  vcn_id            = oci_core_vcn.penthus.id
  cidr_block        = "10.0.1.0/24"
  display_name      = "penthus-public-lb"
  dns_label         = "publb"
  security_list_ids = [oci_core_security_list.public_lb.id]
  route_table_id    = oci_core_route_table.public.id

  freeform_tags = local.common_tags
}

# Private Subnet - Application
resource "oci_core_subnet" "private_app" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.penthus.id
  cidr_block                 = "10.0.2.0/24"
  display_name               = "penthus-private-app"
  dns_label                  = "privapp"
  prohibit_public_ip_on_vnic = true
  security_list_ids          = [oci_core_security_list.private_app.id]
  route_table_id             = oci_core_route_table.private.id

  freeform_tags = local.common_tags
}

# Private Subnet - GPU
resource "oci_core_subnet" "private_gpu" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.penthus.id
  cidr_block                 = "10.0.3.0/24"
  display_name               = "penthus-private-gpu"
  dns_label                  = "privgpu"
  prohibit_public_ip_on_vnic = true
  security_list_ids          = [oci_core_security_list.private_gpu.id]
  route_table_id             = oci_core_route_table.private.id

  freeform_tags = local.common_tags
}

# Private Subnet - Data
resource "oci_core_subnet" "private_data" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.penthus.id
  cidr_block                 = "10.0.4.0/24"
  display_name               = "penthus-private-data"
  dns_label                  = "privdata"
  prohibit_public_ip_on_vnic = true
  security_list_ids          = [oci_core_security_list.private_data.id]
  route_table_id             = oci_core_route_table.private.id

  freeform_tags = local.common_tags
}

# Security List - Public LB
resource "oci_core_security_list" "public_lb" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.penthus.id
  display_name   = "penthus-public-lb-sl"

  ingress_security_rules {
    protocol  = "6" # TCP
    source    = "0.0.0.0/0"
    stateless = false
    tcp_options {
      min = 443
      max = 443
    }
  }

  ingress_security_rules {
    protocol  = "6" # TCP
    source    = "0.0.0.0/0"
    stateless = false
    tcp_options {
      min = 80
      max = 80
    }
  }

  egress_security_rules {
    protocol    = "6"
    destination = "10.0.2.0/24"
    stateless   = false
    tcp_options {
      min = 8000
      max = 8000
    }
  }

  freeform_tags = local.common_tags
}

# Security List - Private App
resource "oci_core_security_list" "private_app" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.penthus.id
  display_name   = "penthus-private-app-sl"

  ingress_security_rules {
    protocol  = "6"
    source    = "10.0.1.0/24"
    stateless = false
    tcp_options {
      min = 8000
      max = 8000
    }
  }

  ingress_security_rules {
    protocol  = "6"
    source    = "10.0.2.0/24"
    stateless = false
  }

  ingress_security_rules {
    protocol  = "6"
    source    = "10.0.3.0/24"
    stateless = false
  }

  egress_security_rules {
    protocol    = "6"
    destination = "10.0.4.0/24"
    stateless   = false
  }

  egress_security_rules {
    protocol    = "6"
    destination = "10.0.3.0/24"
    stateless   = false
  }

  egress_security_rules {
    protocol    = "6"
    destination = data.oci_core_services.all.services[0].cidr_block
    destination_type = "SERVICE_CIDR_BLOCK"
    stateless   = false
  }

  freeform_tags = local.common_tags
}

# Security List - Private GPU
resource "oci_core_security_list" "private_gpu" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.penthus.id
  display_name   = "penthus-private-gpu-sl"

  ingress_security_rules {
    protocol  = "6"
    source    = "10.0.2.0/24"
    stateless = false
    tcp_options {
      min = 8000
      max = 8000
    }
  }

  egress_security_rules {
    protocol    = "6"
    destination = data.oci_core_services.all.services[0].cidr_block
    destination_type = "SERVICE_CIDR_BLOCK"
    stateless   = false
  }

  freeform_tags = local.common_tags
}

# Security List - Private Data
resource "oci_core_security_list" "private_data" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.penthus.id
  display_name   = "penthus-private-data-sl"

  ingress_security_rules {
    protocol  = "6"
    source    = "10.0.2.0/24"
    stateless = false
  }

  egress_security_rules {
    protocol    = "6"
    destination = data.oci_core_services.all.services[0].cidr_block
    destination_type = "SERVICE_CIDR_BLOCK"
    stateless   = false
  }

  freeform_tags = local.common_tags
}

# Data sources
data "oci_core_services" "all" {
  filter {
    name   = "name"
    values = ["All .* Services In Oracle Services Network"]
    regex  = true
  }
}

# Outputs
output "vcn_id" {
  value = oci_core_vcn.penthus.id
}

output "public_subnet_id" {
  value = oci_core_subnet.public_lb.id
}

output "private_app_subnet_id" {
  value = oci_core_subnet.private_app.id
}

output "private_gpu_subnet_id" {
  value = oci_core_subnet.private_gpu.id
}

output "private_data_subnet_id" {
  value = oci_core_subnet.private_data.id
}
