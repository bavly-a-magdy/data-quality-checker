import pandas as pd
from dq_checker.checks.types import check_types
def test_type_mismatch_and_override():
    result=check_types(pd.DataFrame({"amount":["1","2","abc"]}),"x.csv")
    assert result.iloc[0]["bad value"]=="abc"
    forced=check_types(pd.DataFrame({"amount":["1","2","abc"]}),"x.csv",{"amount":"number"})
    assert len(forced)==1
