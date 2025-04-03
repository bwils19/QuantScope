"""Add file metadata fields for security

Revision ID: add_file_metadata_fields
Revises: d8f984b3c2b5
Create Date: 2025-04-03 15:16:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_file_metadata_fields'
down_revision = 'd8f984b3c2b5'
branch_labels = None
depends_on = None


def upgrade():
    # Add file metadata fields to the uploaded_files table
    op.create_table(
        'uploaded_files',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('mime_type', sa.String(length=255), nullable=False),
        sa.Column('file_hash', sa.String(length=64), nullable=False),
        sa.Column('upload_date', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('validation_result', sa.Text(), nullable=True),
        sa.Column('is_processed', sa.Boolean(), nullable=False, default=False),
        sa.Column('processed_date', sa.DateTime(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    
    # Add index for faster lookups
    op.create_index(op.f('ix_uploaded_files_user_id'), 'uploaded_files', ['user_id'], unique=False)
    op.create_index(op.f('ix_uploaded_files_file_hash'), 'uploaded_files', ['file_hash'], unique=False)
    op.create_index(op.f('ix_uploaded_files_upload_date'), 'uploaded_files', ['upload_date'], unique=False)


def downgrade():
    # Drop the uploaded_files table
    op.drop_index(op.f('ix_uploaded_files_upload_date'), table_name='uploaded_files')
    op.drop_index(op.f('ix_uploaded_files_file_hash'), table_name='uploaded_files')
    op.drop_index(op.f('ix_uploaded_files_user_id'), table_name='uploaded_files')
    op.drop_table('uploaded_files')