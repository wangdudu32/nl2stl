from nl2stl_app.converter import STLJSONToStringConverter


def predicate(signal, relation, value):
    return {
        "nodeType": "predicate",
        "left": {"exprType": "signal", "name": signal},
        "relation": relation,
        "right": {"exprType": "constant", "value": value},
    }


def test_converter_removes_only_redundant_parentheses():
    ast = {
        "nodeType": "temporal",
        "operator": "always",
        "operands": [
            {
                "nodeType": "boolean",
                "operator": "implies",
                "operands": [
                    {
                        "nodeType": "edge",
                        "operator": "fall",
                        "mode": "strict",
                        "operand": predicate("ttc", "<", 2.5),
                    },
                    {
                        "nodeType": "temporal",
                        "operator": "eventually",
                        "interval": {
                            "lower": 0,
                            "upper": 0.5,
                            "lowerInclusive": True,
                            "upperInclusive": True,
                        },
                        "operands": [
                            {
                                "nodeType": "boolean",
                                "operator": "and",
                                "operands": [
                                    predicate("collision_warning", "==", 1),
                                    predicate("braking_request", "==", 1),
                                ],
                            }
                        ],
                    },
                ],
            }
        ],
    }
    stl = STLJSONToStringConverter().convert(ast)
    assert stl == (
        "always (fall(ttc < 2.5) -> eventually[0:0.5] "
        "(collision_warning == 1 and braking_request == 1))"
    )


def test_arithmetic_parentheses_are_kept_when_semantically_required():
    ast = {
        "nodeType": "predicate",
        "left": {
            "exprType": "binary",
            "operator": "divide",
            "left": {"exprType": "signal", "name": "distance"},
            "right": {
                "exprType": "binary",
                "operator": "add",
                "left": {"exprType": "signal", "name": "speed"},
                "right": {"exprType": "constant", "value": 1},
            },
        },
        "relation": ">",
        "right": {"exprType": "constant", "value": 2},
    }
    assert STLJSONToStringConverter().convert(ast) == "distance / (speed + 1) > 2"
