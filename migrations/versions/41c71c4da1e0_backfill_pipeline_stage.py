"""Backfill pipeline stage

Revision ID: 41c71c4da1e0
Revises: 94ffa7326f7a
Create Date: 2026-07-30 14:09:33.951524

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '41c71c4da1e0'
down_revision: Union[str, Sequence[str], None] = '94ffa7326f7a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


from sqlalchemy.orm import Session
from app.models import Organisation, PipelineStage

def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    session = Session(bind=bind)
    
    orgs = session.query(Organisation).all()
    for org in orgs:
        if org.research_runs:
            latest_run = org.research_runs[0]
            if latest_run.assessment:
                if latest_run.assessment.pursuit_gate == 'pass':
                    org.pipeline_stage = PipelineStage.qualified
                else:
                    org.pipeline_stage = PipelineStage.disqualified
            elif latest_run.status.value in ['queued', 'researching', 'extracting', 'scoring']:
                org.pipeline_stage = PipelineStage.researching
                
    session.commit()


def downgrade() -> None:
    """Downgrade schema."""
    pass
