import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import Session

from app.db import Base
from app.models import User


def test_unknown_role_is_rejected():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        db.add(User(name="Zed", role="boss"))
        with pytest.raises(StatementError):
            db.commit()
