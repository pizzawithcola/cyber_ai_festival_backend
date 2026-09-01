"""add_score_to_questions

Revision ID: a4b5c6d7e8f9
Revises: a3b4c5d6e7f8
Create Date: 2026-09-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4b5c6d7e8f9'
down_revision: Union[str, None] = 'a3b4c5d6e7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add score column with server_default 1000 so existing rows get 1000
    op.add_column('questions', sa.Column('score', sa.Integer(), nullable=False, server_default='1000'))


def downgrade() -> None:
    op.drop_column('questions', 'score')
