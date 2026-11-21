import pandas as pd
from dq_checker.checks.duplicates import check_duplicates
def test_duplicate_rows_and_keys():
    df=pd.DataFrame({"id":[1,2,2,2],"x":["a","b","c","c"]})
    result=check_duplicates(df,"x.csv",["id"])
    assert {"duplicate row","duplicate key"}.issubset(set(result["issue type"]))
    assert 4 in result["row number"].tolist()
    assert len(result[result["issue type"]=="duplicate row"])==2
