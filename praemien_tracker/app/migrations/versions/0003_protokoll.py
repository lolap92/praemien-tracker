"""protokoll

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'protokoll',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('zeitpunkt', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('tabelle', sa.String(length=50), nullable=False),
        sa.Column('objekt_id', sa.Integer(), nullable=False),
        sa.Column('deal_id', sa.Integer(), nullable=True),
        sa.Column('aktion', sa.String(length=20), nullable=False),
        sa.Column('feld', sa.String(length=100), nullable=True),
        sa.Column('alter_wert', sa.Text(), nullable=True),
        sa.Column('neuer_wert', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_protokoll_zeitpunkt'), 'protokoll', ['zeitpunkt'], unique=False)
    op.create_index(op.f('ix_protokoll_deal_id'), 'protokoll', ['deal_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_protokoll_deal_id'), table_name='protokoll')
    op.drop_index(op.f('ix_protokoll_zeitpunkt'), table_name='protokoll')
    op.drop_table('protokoll')
