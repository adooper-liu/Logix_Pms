"""出边 match_conditions 优先于 process_rule。"""

from app.services.forms import pick_target_from_edges


def test_pick_target_matches_edge_conditions():
    outgoing = [
        {
            "dst": "n5",
            "match": [{"field": "approved", "op": "eq", "value": "是"}],
        },
        {
            "dst": "n6",
            "match": [{"field": "approved", "op": "eq", "value": "否"}],
        },
    ]
    assert pick_target_from_edges(outgoing, {"approved": "是"}) == "n5"
    assert pick_target_from_edges(outgoing, {"approved": "否"}) == "n6"
    assert pick_target_from_edges(outgoing, {"approved": "待定"}) is None


def test_pick_target_falls_back_to_default():
    outgoing = [
        {
            "dst": "n5",
            "match": [{"field": "approved", "op": "eq", "value": "是"}],
        },
        {"dst": "n6", "is_default": True},
    ]
    assert pick_target_from_edges(outgoing, {"approved": "否"}) == "n6"
    assert pick_target_from_edges(outgoing, {"approved": "是"}) == "n5"
