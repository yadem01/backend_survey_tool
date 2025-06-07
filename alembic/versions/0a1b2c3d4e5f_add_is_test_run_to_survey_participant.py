"""add_is_test_run_to_survey_participant

Revision ID: 0a1b2c3d4e5f
Revises: fc125248c2cd
Create Date: 2025-06-30 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0a1b2c3d4e5f'
down_revision: Union[str, None] = 'fc125248c2cd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('survey_participants', sa.Column('is_test_run', sa.Boolean(), nullable=True, server_default=sa.text('false')))


def downgrade() -> None:
    op.drop_column('survey_participants', 'is_test_run')
