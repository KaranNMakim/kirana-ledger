import datetime as dt

import pytest

from app.core.parser import RuleParser
from app.core.products import ProductCatalog
from app.kg.graph_store import NetworkXSQLiteStore
from app.kg.ontology import load_ontology
from app.kg.provenance import Provenance

TODAY = dt.date(2025, 11, 30)


@pytest.fixture(scope="session")
def onto():
    return load_ontology()


@pytest.fixture(scope="session")
def catalog(onto):
    return ProductCatalog(onto)


@pytest.fixture(scope="session")
def parser(catalog):
    return RuleParser(catalog)


@pytest.fixture
def parse(parser):
    return lambda text: parser.parse(text, TODAY)


CUSTOMERS = [
    ("cust:ramesh-patel", "Ramesh Patel", "Ramesh", "Patel", "m"),
    ("cust:ramesh-shah", "Ramesh Shah", "Ramesh", "Shah", "m"),
    ("cust:meena-joshi", "Meena Joshi", "Meena", "Joshi", "f"),
    ("cust:suresh-mehta", "Suresh Mehta", "Suresh", "Mehta", "m"),
    ("cust:kishore-desai", "Kishore Desai", "Kishore", "Desai", "m"),
    ("cust:rakesh-verma", "Rakesh Verma", "Rakesh", "Verma", "m"),
]


@pytest.fixture
def store(onto):
    s = NetworkXSQLiteStore(onto)
    prov = Provenance.seed("test")
    s.upsert_node("shop:main", "Shop", {"name": "Test Kirana"}, prov)
    for cid, name, given, sur, g in CUSTOMERS:
        s.upsert_node(cid, "Customer", {"name": name, "given_name": given, "surname": sur, "gender": g}, prov)
    return s
