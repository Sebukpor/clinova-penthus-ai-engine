"""Initialize Clinova Penthus AI Engine schema

Revision ID: 20240602000000
Revises:
Create Date: 2024-06-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20240602000000'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # tenants
    op.create_table(
        'tenants',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('settings', postgresql.JSONB(), server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )

    # users
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=True),
        sa.Column('roles', postgresql.JSONB(), server_default='[]'),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('api_key_hash', sa.String(255), nullable=True),
        sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('tenant_id', 'email', name='uq_users_tenant_email'),
    )

    # encounters
    op.create_table(
        'encounters',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('patient_ref', sa.String(255), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )

    # documents
    op.create_table(
        'documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('encounter_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('encounters.id'), nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('object_uri', sa.Text(), nullable=True),
        sa.Column('mime_type', sa.String(100), nullable=True),
        sa.Column('language', sa.String(10), nullable=True),
        sa.Column('file_size_bytes', sa.Integer(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('tenant_id', 'content_hash', name='uq_documents_tenant_hash'),
    )
    op.create_index('idx_documents_tenant_encounter', 'documents', ['tenant_id', 'encounter_id'])

    # ocr_results
    op.create_table(
        'ocr_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id'), nullable=False),
        sa.Column('raw_text', sa.Text(), nullable=False),
        sa.Column('entities', postgresql.JSONB(), server_default='[]'),
        sa.Column('layout', postgresql.JSONB(), server_default='{}'),
        sa.Column('language', sa.String(10), nullable=False, server_default='en'),
        sa.Column('confidence', sa.Numeric(5, 4), nullable=True),
        sa.Column('model_version', sa.String(100), nullable=False),
        sa.Column('prompt_version', sa.String(50), nullable=False),
        sa.Column('processing_time_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('tenant_id', 'document_id', name='uq_ocr_tenant_document'),
    )
    op.create_index('idx_ocr_document_lookup', 'ocr_results', ['tenant_id', 'document_id'])

    # soap_results
    op.create_table(
        'soap_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('encounter_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('encounters.id'), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id'), nullable=True),
        sa.Column('subjective', sa.Text(), nullable=True),
        sa.Column('objective', sa.Text(), nullable=True),
        sa.Column('assessment', sa.Text(), nullable=True),
        sa.Column('plan', sa.Text(), nullable=True),
        sa.Column('model_version', sa.String(100), nullable=False),
        sa.Column('prompt_version', sa.String(50), nullable=False),
        sa.Column('processing_time_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_soap_encounter', 'soap_results', ['tenant_id', 'encounter_id'])

    # entity_results
    op.create_table(
        'entity_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('encounter_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('encounters.id'), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id'), nullable=True),
        sa.Column('entities', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('model_version', sa.String(100), nullable=False),
        sa.Column('prompt_version', sa.String(50), nullable=False),
        sa.Column('processing_time_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_entities_encounter', 'entity_results', ['tenant_id', 'encounter_id'])

    # normalization_results
    op.create_table(
        'normalization_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('encounter_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('encounters.id'), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id'), nullable=True),
        sa.Column('normalized_terms', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('model_version', sa.String(100), nullable=False),
        sa.Column('prompt_version', sa.String(50), nullable=False),
        sa.Column('processing_time_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_normalization_encounter', 'normalization_results', ['tenant_id', 'encounter_id'])

    # summary_results
    op.create_table(
        'summary_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('encounter_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('encounters.id'), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id'), nullable=True),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('key_findings', postgresql.JSONB(), server_default='[]'),
        sa.Column('recommended_follow_up', postgresql.JSONB(), server_default='[]'),
        sa.Column('model_version', sa.String(100), nullable=False),
        sa.Column('prompt_version', sa.String(50), nullable=False),
        sa.Column('processing_time_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_summary_encounter', 'summary_results', ['tenant_id', 'encounter_id'])

    # gap_results
    op.create_table(
        'gap_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('encounter_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('encounters.id'), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id'), nullable=True),
        sa.Column('missing_information', postgresql.JSONB(), server_default='[]'),
        sa.Column('quality_warnings', postgresql.JSONB(), server_default='[]'),
        sa.Column('suggestions', postgresql.JSONB(), server_default='[]'),
        sa.Column('model_version', sa.String(100), nullable=False),
        sa.Column('prompt_version', sa.String(50), nullable=False),
        sa.Column('processing_time_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_gap_encounter', 'gap_results', ['tenant_id', 'encounter_id'])

    # translation_results
    op.create_table(
        'translation_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('encounter_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('encounters.id'), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id'), nullable=True),
        sa.Column('source_language', sa.String(10), nullable=False),
        sa.Column('target_language', sa.String(10), nullable=False),
        sa.Column('source_text', sa.Text(), nullable=False),
        sa.Column('translated_text', sa.Text(), nullable=False),
        sa.Column('confidence', sa.Numeric(5, 4), nullable=True),
        sa.Column('model_version', sa.String(100), nullable=False),
        sa.Column('prompt_version', sa.String(50), nullable=False),
        sa.Column('processing_time_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_translation_encounter', 'translation_results', ['tenant_id', 'encounter_id'])

    # clinical_contexts
    op.create_table(
        'clinical_contexts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('encounter_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('encounters.id'), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id'), nullable=True),
        sa.Column('state', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('tenant_id', 'encounter_id', 'document_id', name='uq_context_tenant_encounter_doc'),
    )
    op.create_index('idx_context_encounter_lookup', 'clinical_contexts', ['tenant_id', 'encounter_id'])

    # prompt_versions
    op.create_table(
        'prompt_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('prompt_key', sa.String(50), nullable=False),
        sa.Column('version', sa.String(20), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('capability', sa.String(30), nullable=False),
        sa.Column('model_repo', sa.String(200), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='draft'),
        sa.Column('environment', sa.String(20), nullable=False, server_default='development'),
        sa.Column('response_format', sa.String(20), nullable=False, server_default='json'),
        sa.Column('schema_ref', sa.String(100), nullable=False),
        sa.Column('temperature', sa.Numeric(3, 2), nullable=False, server_default='0.1'),
        sa.Column('max_tokens', sa.Integer(), nullable=False, server_default='1200'),
        sa.Column('system_message', sa.Text(), nullable=False),
        sa.Column('template', sa.Text(), nullable=False),
        sa.Column('variables', postgresql.JSONB(), server_default='[]'),
        sa.Column('is_ocr_breaking', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_by', sa.String(100), nullable=False),
        sa.Column('metadata', postgresql.JSONB(), server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('prompt_key', 'version', name='uq_prompt_key_version'),
    )
    op.create_index('idx_prompt_capability_env', 'prompt_versions', ['capability', 'environment', 'status'])

    # inference_logs
    op.create_table(
        'inference_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('request_id', sa.String(100), nullable=False),
        sa.Column('workflow', sa.String(30), nullable=False),
        sa.Column('model_repo', sa.String(200), nullable=False),
        sa.Column('model_version', sa.String(100), nullable=False),
        sa.Column('prompt_version', sa.String(50), nullable=False),
        sa.Column('latency_ms', sa.Integer(), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('validation_status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_inference_workflow_time', 'inference_logs', ['workflow', 'created_at'])
    op.create_index('idx_inference_request', 'inference_logs', ['request_id'])
    op.create_index('idx_inference_tenant', 'inference_logs', ['tenant_id', 'created_at'])

    # terminology_cache
    op.create_table(
        'terminology_cache',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('system', sa.String(20), nullable=False),
        sa.Column('query_hash', sa.String(64), nullable=False),
        sa.Column('query_text', sa.Text(), nullable=False),
        sa.Column('candidates', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('tenant_id', 'system', 'query_hash', name='uq_terminology_tenant_system_hash'),
    )
    op.create_index('idx_terminology_lookup', 'terminology_cache', ['tenant_id', 'system', 'query_hash'])

    # fhir_resources
    op.create_table(
        'fhir_resources',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('encounter_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('encounters.id'), nullable=False),
        sa.Column('resource_type', sa.String(50), nullable=False),
        sa.Column('resource', postgresql.JSONB(), nullable=False),
        sa.Column('validation_status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('delivery_status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('delivery_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_delivery_error', sa.Text(), nullable=True),
        sa.Column('model_version', sa.String(100), nullable=False),
        sa.Column('prompt_version', sa.String(50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_fhir_encounter_type', 'fhir_resources', ['tenant_id', 'encounter_id', 'resource_type'])

    # audit_logs
    op.create_table(
        'audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('actor_id', sa.String(100), nullable=True),
        sa.Column('actor_type', sa.String(20), nullable=False, server_default='user'),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('resource_type', sa.String(50), nullable=False),
        sa.Column('resource_id', sa.String(100), nullable=True),
        sa.Column('ip_address', postgresql.INET(), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('request_id', sa.String(100), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_audit_tenant_time', 'audit_logs', ['tenant_id', 'created_at'])
    op.create_index('idx_audit_actor', 'audit_logs', ['actor_id', 'created_at'])
    op.create_index('idx_audit_action', 'audit_logs', ['action', 'resource_type'])

    # workflow_state
    op.create_table(
        'workflow_state',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('request_id', sa.String(100), nullable=False),
        sa.Column('workflow', sa.String(30), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('input_data', postgresql.JSONB(), server_default='{}'),
        sa.Column('output_data', postgresql.JSONB(), server_default='{}'),
        sa.Column('error_info', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_retries', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('tenant_id', 'request_id', name='uq_workflow_tenant_request'),
    )
    op.create_index('idx_workflow_status', 'workflow_state', ['status', 'next_retry_at'])

    # terminology_requests
    op.create_table(
        'terminology_requests',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('encounter_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('encounters.id'), nullable=True),
        sa.Column('system', sa.String(20), nullable=False),
        sa.Column('query_terms', postgresql.JSONB(), nullable=False),
        sa.Column('response_count', sa.Integer(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_terminology_req_encounter', 'terminology_requests', ['tenant_id', 'encounter_id'])


def downgrade() -> None:
    op.drop_table('terminology_requests')
    op.drop_table('workflow_state')
    op.drop_table('audit_logs')
    op.drop_table('fhir_resources')
    op.drop_table('terminology_cache')
    op.drop_table('inference_logs')
    op.drop_table('prompt_versions')
    op.drop_table('clinical_contexts')
    op.drop_table('translation_results')
    op.drop_table('gap_results')
    op.drop_table('summary_results')
    op.drop_table('normalization_results')
    op.drop_table('entity_results')
    op.drop_table('soap_results')
    op.drop_table('ocr_results')
    op.drop_table('documents')
    op.drop_table('encounters')
    op.drop_table('users')
    op.drop_table('tenants')
