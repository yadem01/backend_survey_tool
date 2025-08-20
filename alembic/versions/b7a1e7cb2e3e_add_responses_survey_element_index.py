"""add index on responses.survey_element_id"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b7a1e7cb2e3e'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('ix_responses_survey_element_id', 'responses', ['survey_element_id'])


def downgrade() -> None:
    op.drop_index('ix_responses_survey_element_id', table_name='responses')
