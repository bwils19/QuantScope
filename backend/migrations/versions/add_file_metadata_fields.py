"""Add file metadata fields to PortfolioFiles

Revision ID: add_file_metadata_fields
Revises: d8f984b3c2b5
Create Date: 2025-04-03 13:42:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_file_metadata_fields'
down_revision = 'd8f984b3c2b5'
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns to portfolio_files table
    op.add_column('portfolio_files', sa.Column('file_content_type', sa.String(length=100), nullable=True))
    op.add_column('portfolio_files', sa.Column('file_size', sa.Integer(), nullable=True))
    op.add_column('portfolio_files', sa.Column('processed', sa.Boolean(), nullable=True, default=False))


def downgrade():
    # Remove columns from portfolio_files table
    op.drop_column('portfolio_files', 'file_content_type')
    op.drop_column('portfolio_files', 'file_size')
    op.drop_column('portfolio_files', 'processed')