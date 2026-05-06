"""initial_nexus_tables

Revision ID: 60c75d18e9ed
Revises: 
Create Date: 2026-05-07 04:42:23.421868

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '60c75d18e9ed'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create nexus_apps
    op.create_table(
        'nexus_apps',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('app_name', sa.String(length=100), nullable=False),
        sa.Column('api_key_hash', sa.String(length=255), nullable=False),
        sa.Column('api_key_prefix', sa.String(length=10), nullable=False),
        sa.Column('webhook_secret', sa.String(length=255), nullable=True),
        sa.Column('callback_url', sa.String(length=500), nullable=True),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('is_admin', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('app_name')
    )
    op.create_index('idx_api_key_prefix', 'nexus_apps', ['api_key_prefix'])

    # 2. Create nexus_app_permissions
    op.create_table(
        'nexus_app_permissions',
        sa.Column('app_id', sa.String(length=36), nullable=False),
        sa.Column('endpoint', sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(['app_id'], ['nexus_apps.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('app_id', 'endpoint')
    )

    # 3. Create nexus_jobs
    op.create_table(
        'nexus_jobs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('app_id', sa.String(length=36), nullable=False),
        sa.Column('app_name', sa.String(length=100), nullable=False),
        sa.Column('caller_user_id', sa.String(length=100), nullable=True),
        sa.Column('caller_user_name', sa.String(length=100), nullable=True),
        sa.Column('endpoint', sa.String(length=100), nullable=False),
        sa.Column('request_payload', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='queued'),
        sa.Column('result_payload', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('cost_usd', sa.Numeric(precision=10, scale=6), nullable=False, server_default='0.000000'),
        sa.Column('queued_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('webhook_url', sa.String(length=500), nullable=True),
        sa.Column('webhook_sent', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('webhook_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('webhook_last_attempt', sa.DateTime(), nullable=True),
        sa.Column('webhook_failed', sa.Boolean(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['app_id'], ['nexus_apps.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_app_status', 'nexus_jobs', ['app_id', 'status'])
    op.create_index('idx_status_queued', 'nexus_jobs', ['status', 'queued_at'])
    op.create_index('idx_caller', 'nexus_jobs', ['caller_user_id'])

    # 4. Create nexus_usage_log
    op.create_table(
        'nexus_usage_log',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('app_id', sa.String(length=36), nullable=False),
        sa.Column('app_name', sa.String(length=100), nullable=False),
        sa.Column('caller_user_id', sa.String(length=100), nullable=True),
        sa.Column('caller_user_name', sa.String(length=100), nullable=True),
        sa.Column('endpoint', sa.String(length=100), nullable=False),
        sa.Column('response_mode', sa.String(length=10), nullable=False),
        sa.Column('job_id', sa.String(length=36), nullable=True),
        sa.Column('model_used', sa.String(length=100), nullable=True),
        sa.Column('prompt_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('completion_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cost_usd', sa.Numeric(precision=10, scale=6), nullable=False, server_default='0.000000'),
        sa.Column('latency_ms', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status_code', sa.Integer(), nullable=False, server_default='200'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('requested_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['app_id'], ['nexus_apps.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['job_id'], ['nexus_jobs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_app_date', 'nexus_usage_log', ['app_id', 'requested_at'])
    op.create_index('idx_endpoint_date', 'nexus_usage_log', ['endpoint', 'requested_at'])
    op.create_index('idx_caller_date', 'nexus_usage_log', ['caller_user_id', 'requested_at'])
    op.create_index('idx_requested_at', 'nexus_usage_log', ['requested_at'])

    # 5. Create nexus_rate_limits
    op.create_table(
        'nexus_rate_limits',
        sa.Column('app_id', sa.String(length=36), nullable=False),
        sa.Column('endpoint', sa.String(length=100), nullable=False),
        sa.Column('requests_per_hour', sa.Integer(), nullable=False, server_default='200'),
        sa.Column('max_tokens_per_day', sa.Integer(), nullable=False, server_default='2000000'),
        sa.ForeignKeyConstraint(['app_id'], ['nexus_apps.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('app_id', 'endpoint')
    )


def downgrade() -> None:
    op.drop_table('nexus_rate_limits')
    op.drop_table('nexus_usage_log')
    op.drop_table('nexus_jobs')
    op.drop_table('nexus_app_permissions')
    op.drop_table('nexus_apps')
