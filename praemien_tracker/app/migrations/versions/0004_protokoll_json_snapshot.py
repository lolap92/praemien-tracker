"""protokoll json snapshot und kontext

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('protokoll', sa.Column('json_snapshot', sa.Text(), nullable=True))
    op.add_column('protokoll', sa.Column('bank_name', sa.String(length=100), nullable=True))
    op.add_column('protokoll', sa.Column('inhaber_name', sa.String(length=100), nullable=True))
    op.add_column('protokoll', sa.Column('kontoart', sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column('protokoll', 'kontoart')
    op.drop_column('protokoll', 'inhaber_name')
    op.drop_column('protokoll', 'bank_name')
    op.drop_column('protokoll', 'json_snapshot')
