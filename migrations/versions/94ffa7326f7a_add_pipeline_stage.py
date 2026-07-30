"""Add pipeline stage

Revision ID: 94ffa7326f7a
Revises: c18217fe5e26
Create Date: 2026-07-30 13:57:19.712093

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '94ffa7326f7a'
down_revision: Union[str, Sequence[str], None] = 'c18217fe5e26'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pipeline_stage_enum = sa.Enum('discovered', 'researching', 'qualified', 'disqualified', 'outreach', 'meeting_scheduled', 'closed_won', 'closed_lost', name='pipelinestage')
    pipeline_stage_enum.create(op.get_bind(), checkfirst=True)
    op.add_column('organisations', sa.Column('pipeline_stage', pipeline_stage_enum, nullable=False, server_default='discovered'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('organisations', 'pipeline_stage')
    pipeline_stage_enum = sa.Enum('discovered', 'researching', 'qualified', 'disqualified', 'outreach', 'meeting_scheduled', 'closed_won', 'closed_lost', name='pipelinestage')
    pipeline_stage_enum.drop(op.get_bind(), checkfirst=True)
