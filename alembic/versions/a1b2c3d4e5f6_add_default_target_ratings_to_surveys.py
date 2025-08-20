"""add_default_target_ratings_to_surveys

Revision ID: a1b2c3d4e5f6
Revises: 0a1b2c3d4e5f
Create Date: 2025-07-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "0a1b2c3d4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "surveys",
        sa.Column("default_target_ratings", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("surveys", "default_target_ratings")
