import logging
import sqlite3
from sqlite3 import Connection

import libcst as cst
import pytest

from src.bound_strings import bind, SQLQuery


@pytest.fixture(autouse=True)
def _debug_logging():
    import logging

    logging.basicConfig(level=logging.DEBUG)

    yield


@pytest.fixture(scope="session")
def db_seed():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
            CREATE TABLE student (
                id INTEGER PRIMARY KEY NOT NULL,
                name TEXT NOT NULL,
                grade INTEGER NOT NULL
            )
        """
    )
    conn.commit()

    conn.execute(
        """
            INSERT INTO student (name, grade) VALUES
                ('Alice', 100),
                ('Bob', 90),
                ('Ivan', 80),
                ('Charlie', 70),
                ('David', 60),
                ('Eve', 50),
                ('Frank', 40),
                ('Grace', 30),
                ('Heidi', 20),
                ('Robert', 10)
        """
    )
    conn.commit()
    yield conn

    conn.execute("DROP TABLE student")
    conn.commit()
    conn.close()


@pytest.fixture()
def db(db_seed: Connection):
    db_seed.execute("BEGIN TRANSACTION")
    yield db_seed
    db_seed.execute("ROLLBACK")


def test_db_initialized(db: Connection):
    assert db.execute("SELECT COUNT(*) FROM student").fetchone()[0] == 10


def test_injection(db: Connection):
    boom = """Something' OR id = 1; --"""
    assert (
        db.execute(
            f"""
    SELECT 
        grade 
    FROM student 
    WHERE 
        name = '{boom}' 
    """
        ).fetchone()[0]
        == 100
    )


class SQLiteQuery(SQLQuery):
    def bind_expression(self, value: cst) -> None:
        # Todo support f-string spec and conversion flags
        self.values.append(value.expression)
        self.template += "?"


@bind(SQLiteQuery)
def without_injection():
    not_so_boom = """Something' OR id = 1; --"""
    return f"""
        SELECT 
            grade 
        FROM student 
        WHERE 
            name = {not_so_boom} 
    """


def test_no_injection(db: Connection):
    query = without_injection()
    assert isinstance(query, SQLQuery)
    logging.error(query)
    assert db.execute(query.template, query.values).fetchall() == []
