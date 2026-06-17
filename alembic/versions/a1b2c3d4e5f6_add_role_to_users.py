"""add_role_to_users

Revision ID: a1b2c3d4e5f6
Revises: cc9a6305c973
Create Date: 2026-02-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'cc9a6305c973'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add role column with server_default 'player' so existing rows get 'player'
    op.add_column('users', sa.Column('role', sa.String(32), nullable=False, server_default='player'))


def downgrade() -> None:
    op.drop_column('users', 'role')
